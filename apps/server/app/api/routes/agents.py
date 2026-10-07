"""Routes: create/list/read/update/delete/fork/submit/chat for the current user's agents."""

import json
import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user_id, limit_llm_user
from app.core.config import get_settings
from app.db.session import get_db
from app.llm.agent_runtime import StreamEvent
from app.llm.client import LlmClient
from app.llm.fallback import (
    LlmModelResolutionError,
    run_agent_chat_stream_with_model_fallback,
    run_agent_chat_with_model_fallback,
)
from app.llm.guard import BLOCK_MESSAGE_AGENT_CONFIG
from app.models.conversation import MessageRole
from app.models.enums import AgentStatus
from app.schemas.agent import (
    AgentCreate,
    AgentDetail,
    AgentListItem,
    AgentUpdate,
    ChatRequest,
    ChatResponse,
    ConfigSnapshot,
    PreviewChatRequest,
)
from app.services import agents as agents_service
from app.services import conversations as conv_service
from app.services import knowledge as knowledge_service
from app.services import prompt_guard

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


def _to_detail(agent) -> AgentDetail:
    return AgentDetail(
        **agents_service.to_list_item(agent).model_dump(),
        config=agents_service.current_config(agent),
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
    return _to_detail(agent)


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
    return _to_detail(agent)


@router.delete("/{agent_id}")
async def delete_agent(
    agent_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    agent = await _get_owned_agent(db, agent_id, user_id)
    await agents_service.archive_agent(db, agent)
    return {"id": str(agent_id), "status": AgentStatus.archived}


@router.post("/{agent_id}/fork", response_model=AgentDetail)
async def fork_agent(
    agent_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    agent = await agents_service.get_accessible_agent(db, agent_id, user_id)
    if agent is None:
        raise HTTPException(status_code=404, detail="not_found")
    forked = await agents_service.fork_agent(db, agent, user_id)
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
    return _to_detail(agent)


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

    conv_id = None
    if payload.conversation_id:
        conv = await conv_service.get_conversation(db, payload.conversation_id, user_id)
        if conv is not None:
            conv_id = conv.id
    if conv_id is None:
        conv = await conv_service.create_conversation(
            db,
            agent_id,
            user_id,
            title=payload.messages[-1].content[:500] if payload.messages else "",
        )
        conv_id = conv.id

    last_user_msg = payload.messages[-1] if payload.messages else None
    if last_user_msg and last_user_msg.role == "user":
        await conv_service.add_message(
            db, conv_id, MessageRole.user, last_user_msg.content
        )

    thread_id = str(conv_id)

    if payload.stream:

        async def run_stream(hardened: ConfigSnapshot):
            async for event in run_agent_chat_stream_with_model_fallback(
                client,
                hardened,
                history=payload.messages,
                temperature=config.temperature,
                primary_model=primary_model,
                default_model=default_model,
                thread_id=thread_id,
            ):
                yield event

        def _sse(event: StreamEvent) -> str:
            payload_dict: dict = {"type": event.type}
            if event.content:
                payload_dict["content"] = event.content
            if event.tool_name:
                payload_dict["tool_name"] = event.tool_name
            if event.tool_args:
                payload_dict["tool_args"] = event.tool_args
            if event.tool_result:
                payload_dict["tool_result"] = event.tool_result
            payload_dict["conversation_id"] = str(conv_id)
            return f"data: {json.dumps(payload_dict)}\n\n"

        async def sse_generator():
            full_reply: list[str] = []
            blocked = False
            try:
                async for event in prompt_guard.guarded_agent_chat_stream(
                    db,
                    route="agents.chat",
                    user_id=user_id,
                    config=config,
                    history=payload.messages,
                    run=run_stream,
                ):
                    if event.type == "token":
                        full_reply.append(event.content)
                    elif event.type == "blocked":
                        blocked = True
                    yield _sse(event)
                if not blocked and full_reply:
                    reply_text = "".join(full_reply).strip()
                    if reply_text:
                        await conv_service.add_message(
                            db, conv_id, MessageRole.assistant, reply_text
                        )
            except prompt_guard.GuardBlockedError as exc:
                yield _sse(StreamEvent(type="blocked", content=exc.message))
            except LlmModelResolutionError:
                yield _sse(StreamEvent(type="error", content="llm_unavailable"))
            yield "data: [DONE]\n\n"

        return StreamingResponse(sse_generator(), media_type="text/event-stream")

    async def run(hardened: ConfigSnapshot) -> str:
        return await run_agent_chat_with_model_fallback(
            client,
            hardened,
            history=payload.messages,
            temperature=config.temperature,
            primary_model=primary_model,
            default_model=default_model,
            thread_id=thread_id,
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

    msg = await conv_service.add_message(db, conv_id, MessageRole.assistant, reply)
    return ChatResponse(reply=reply, conversation_id=conv_id, message_id=msg.id)


@router.post("/preview-chat", response_model=ChatResponse)
async def preview_chat(
    payload: PreviewChatRequest,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(limit_llm_user),
):
    """Teste un agent non encore enregistré : la config vient du client (wizard/onboarding)."""
    config = payload.config
    if not config.system_prompt.strip():
        raise HTTPException(status_code=400, detail="prompt_required")
    default_model = get_settings().llm_default_model
    primary_model = config.model_id or default_model
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
            route="agents.preview-chat",
            user_id=user_id,
            config=config,
            history=payload.messages,
            run=run,
        )
    except LlmModelResolutionError as exc:
        raise HTTPException(status_code=502, detail="llm_unavailable") from exc
    return ChatResponse(reply=reply)
