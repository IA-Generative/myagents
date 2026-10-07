"""Public catalog of published/submitted community & ministry agents."""

import json
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
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
from app.models.conversation import MessageRole
from app.schemas.agent import (
    AgentDetail,
    AgentListItem,
    ChatRequest,
    ChatResponse,
    ConfigSnapshot,
)
from app.services import agents as agents_service
from app.services import conversations as conv_service
from app.services import prompt_guard

router = APIRouter(
    prefix="/catalog", tags=["catalog"], dependencies=[Depends(get_current_user_id)]
)


async def _get_public_agent(db: AsyncSession, agent_id: uuid.UUID):
    agent = await agents_service.get_agent(db, agent_id)
    if agent is None or not agents_service.is_catalog_visible(agent):
        raise HTTPException(status_code=404, detail="not_found")
    return agent


@router.get("", response_model=list[AgentListItem])
async def list_catalog(
    category: str | None = Query(default=None), db: AsyncSession = Depends(get_db)
):
    agents = await agents_service.list_catalog(db, category)
    return [agents_service.to_list_item(a) for a in agents]


@router.get("/{agent_id}", response_model=AgentDetail)
async def get_catalog_agent(agent_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    agent = await _get_public_agent(db, agent_id)
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
):
    """Try out any published/community/ministry agent — no ownership required."""
    agent = await _get_public_agent(db, agent_id)
    config = agents_service.current_config(agent)
    # Le modèle gardé en base vieillit (retiré ou renommé par l'opérateur) : même repli
    # sur le modèle par défaut que pour ses propres agents.
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
                    route="catalog.chat",
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
            route="catalog.chat",
            user_id=user_id,
            config=config,
            history=payload.messages,
            run=run,
        )
    except LlmModelResolutionError as exc:
        raise HTTPException(status_code=502, detail="llm_unavailable") from exc

    msg = await conv_service.add_message(db, conv_id, MessageRole.assistant, reply)
    return ChatResponse(reply=reply, conversation_id=conv_id, message_id=msg.id)
