"""Public catalog of published/submitted community & ministry agents."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user_id, limit_llm_user
from app.db.session import get_db
from app.llm import agent_runtime
from app.llm.client import LlmClient, LlmUnavailableError
from app.schemas.agent import AgentDetail, AgentListItem, ChatRequest, ChatResponse
from app.services import agents as agents_service

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
    _user_id: str = Depends(limit_llm_user),
):
    """Try out any published/community/ministry agent — no ownership required."""
    agent = await _get_public_agent(db, agent_id)
    config = agents_service.current_config(agent)
    client = LlmClient()
    try:
        reply = await agent_runtime.arun_agent_chat(
            client,
            config,
            history=payload.messages,
            model=config.model_id or agent.model_ref,
            temperature=config.temperature,
        )
    except LlmUnavailableError as exc:
        raise HTTPException(status_code=502, detail="llm_unavailable") from exc
    return ChatResponse(reply=reply)
