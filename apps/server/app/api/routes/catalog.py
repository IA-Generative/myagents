"""Public catalog of published/submitted community & ministry agents."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, limit_llm_user
from app.core.config import get_settings
from app.core.security import AuthUser
from app.db.session import get_db
from app.llm.client import LlmClient
from app.llm.fallback import LlmModelResolutionError, run_agent_chat_with_model_fallback
from app.schemas.agent import (
    AgentDetail,
    AgentListItem,
    ChatRequest,
    ChatResponse,
    ConfigSnapshot,
)
from app.services import agents as agents_service
from app.services import prompt_guard

router = APIRouter(prefix="/catalog", tags=["catalog"])


async def _get_public_agent(db: AsyncSession, agent_id: uuid.UUID, user: AuthUser):
    """Un agent partagé avec cette personne (contrat d'agents §Les droits)."""
    agent = await agents_service.get_agent(db, agent_id)
    if agent is None or not agents_service.is_in_catalog(
        agent, user.user_id, user.groups
    ):
        raise HTTPException(status_code=404, detail="not_found")
    return agent


@router.get("", response_model=list[AgentListItem])
async def list_catalog(
    category: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    user: AuthUser = Depends(get_current_user),
):
    agents = await agents_service.list_catalog(db, category, user.user_id, user.groups)
    return [agents_service.to_list_item(a) for a in agents]


@router.get("/{agent_id}", response_model=AgentDetail)
async def get_catalog_agent(
    agent_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: AuthUser = Depends(get_current_user),
):
    agent = await _get_public_agent(db, agent_id, user)
    return AgentDetail(
        **agents_service.to_list_item(agent).model_dump(),
        config=agents_service.current_config(agent),
    )


@router.post("/{agent_id}/chat", response_model=ChatResponse)
async def chat_with_catalog_agent(
    agent_id: uuid.UUID,
    payload: ChatRequest,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(limit_llm_user),
    user: AuthUser = Depends(get_current_user),
):
    """Try out any agent shared with the caller — no ownership required."""
    agent = await _get_public_agent(db, agent_id, user)
    config = agents_service.current_config(agent)
    # Le modèle gardé en base vieillit (retiré ou renommé par l'opérateur) : même repli
    # sur le modèle par défaut que pour ses propres agents.
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
            route="catalog.chat",
            user_id=user_id,
            config=config,
            history=payload.messages,
            run=run,
        )
    except LlmModelResolutionError as exc:
        raise HTTPException(status_code=502, detail="llm_unavailable") from exc
    return ChatResponse(reply=reply)
