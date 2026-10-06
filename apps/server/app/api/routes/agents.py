"""Routes: create/list/read/update/delete/fork/submit/chat for the current user's agents."""

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_current_user_id, limit_llm_user
from app.core.config import get_settings
from app.core.security import AuthUser
from app.db.session import get_db
from app.llm.client import LlmClient
from app.llm.fallback import LlmModelResolutionError, run_agent_chat_with_model_fallback
from app.llm.guard import BLOCK_MESSAGE_AGENT_CONFIG
from app.models.enums import AgentStatus
from app.schemas.agent import (
    AgentCreate,
    AgentDetail,
    AgentListItem,
    AgentUpdate,
    ChatRequest,
    ChatResponse,
    ConfigSnapshot,
)
from app.services import agents as agents_service
from app.services import knowledge as knowledge_service
from app.services import prompt_guard, socle

router = APIRouter(prefix="/agents", tags=["agents"])
logger = logging.getLogger(__name__)


async def _get_owned_agent(db: AsyncSession, agent_id: uuid.UUID, user_id: str):
    agent = await agents_service.get_agent(db, agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail="not_found")
    if agent.creator_id != user_id:
        raise HTTPException(status_code=403, detail="forbidden")
    return agent


def creator_content(config: ConfigSnapshot) -> str:
    """Tout le contenu rédigé par le créateur et servi ensuite aux utilisateurs."""
    return "\n\n".join(
        [config.system_prompt, config.description, config.greeting, *config.examples]
    )


async def _validate_config(
    db: AsyncSession, user_id: str, config: ConfigSnapshot, *, route: str
) -> None:
    """Server-side checks the wizard's client-side validation can't be trusted for."""
    if not await knowledge_service.all_owned_by(db, config.knowledge_ids, user_id):
        raise HTTPException(status_code=422, detail="invalid_knowledge_ids")
    # Garde anti-chaîne d'approvisionnement, quel que soit le statut (brouillon
    # compris) : un créateur ne doit pas pouvoir enregistrer un agent qui embarque
    # un keylogger ou une consigne d'injection.
    await prompt_guard.check_input(
        db,
        route=route,
        text=creator_content(config),
        role="system",
        block_message=BLOCK_MESSAGE_AGENT_CONFIG,
        user_id=user_id,
    )


def _to_detail(agent, socle_etat: str | None = None) -> AgentDetail:
    return AgentDetail(
        **agents_service.to_list_item(agent).model_dump(),
        config=agents_service.current_config(agent),
        socle=socle_etat,
    )


@router.get("", response_model=list[AgentListItem])
async def list_agents(
    db: AsyncSession = Depends(get_db), user_id: str = Depends(get_current_user_id)
):
    agents = await agents_service.list_my_agents(db, user_id)
    return [agents_service.to_list_item(a) for a in agents]


@router.post("", response_model=AgentDetail)
async def create_agent(
    payload: AgentCreate,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    await _validate_config(db, user_id, payload.config, route="agents.create")
    agent = await agents_service.create_agent(db, user_id, payload)
    # La fiche du socle suit la publication (contrat d'agents, §Le socle) ; un brouillon
    # n'en a pas et n'appelle pas le socle.
    etat = (
        await socle.synchroniser(agent) if socle.doit_avoir_une_fiche(agent) else None
    )
    return _to_detail(agent, etat)


@router.get("/{agent_id}", response_model=AgentDetail)
async def get_agent(
    agent_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    agent = await _get_owned_agent(db, agent_id, user_id)
    return _to_detail(agent)


@router.put("/{agent_id}", response_model=AgentDetail)
async def update_agent(
    agent_id: uuid.UUID,
    payload: AgentUpdate,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    agent = await _get_owned_agent(db, agent_id, user_id)
    await _validate_config(db, user_id, payload.config, route="agents.update")
    agent = await agents_service.update_agent(db, agent, payload)
    return _to_detail(agent, await socle.synchroniser(agent))


@router.delete("/{agent_id}")
async def delete_agent(
    agent_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    agent = await _get_owned_agent(db, agent_id, user_id)
    await agents_service.archive_agent(db, agent)
    etat = await socle.synchroniser(agent)
    return {"id": str(agent_id), "status": AgentStatus.archived, "socle": etat}


@router.post("/{agent_id}/fork", response_model=AgentDetail)
async def fork_agent(
    agent_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: AuthUser = Depends(get_current_user),
):
    agent = await agents_service.get_accessible_agent(
        db, agent_id, user.user_id, user.groups
    )
    if agent is None:
        raise HTTPException(status_code=404, detail="not_found")
    forked = await agents_service.fork_agent(db, agent, user.user_id)
    return _to_detail(forked)


@router.post("/{agent_id}/submit", response_model=AgentDetail)
async def submit_agent(
    agent_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    agent = await _get_owned_agent(db, agent_id, user_id)
    # Un agent enregistré avant la garde peut porter un prompt hostile : on recontrôle.
    await _validate_config(
        db, user_id, agents_service.current_config(agent), route="agents.submit"
    )
    agent = await agents_service.submit_agent(db, agent)
    return _to_detail(agent, await socle.synchroniser(agent))


@router.post("/{agent_id}/chat", response_model=ChatResponse)
async def chat_with_agent(
    agent_id: uuid.UUID,
    payload: ChatRequest,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(limit_llm_user),
):
    agent = await _get_owned_agent(db, agent_id, user_id)
    if agent.status == AgentStatus.archived:
        raise HTTPException(status_code=409, detail="agent_archived")
    config = agents_service.current_config(agent)
    default_model = get_settings().llm_default_model
    primary_model = config.model_id or agent.model_ref or default_model
    client = LlmClient()

    async def run(hardened: ConfigSnapshot) -> str:
        return await run_agent_chat_with_model_fallback(
            client,
            hardened,
            history=payload.messages,
            temperature=config.temperature,
            primary_model=primary_model,
            default_model=default_model,
        )

    try:
        reply = await prompt_guard.guarded_agent_chat(
            db,
            route="agents.chat",
            user_id=user_id,
            config=config,
            history=payload.messages,
            run=run,
        )
    except LlmModelResolutionError as exc:
        raise HTTPException(status_code=502, detail="llm_unavailable") from exc
    return ChatResponse(reply=reply)
