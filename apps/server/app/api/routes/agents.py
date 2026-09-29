"""Routes: create/list/read/update/delete/fork/submit/chat for the current user's agents."""

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user_id
from app.db.session import get_db
from app.llm import agent_runtime
from app.llm.client import LlmClient, LlmUnavailableError
from app.models.enums import AgentStatus
from app.schemas.agent import (
    AgentCreate,
    AgentDetail,
    AgentListItem,
    AgentUpdate,
    ChatRequest,
    ChatResponse,
)
from app.services import agents as agents_service

router = APIRouter(prefix="/agents", tags=["agents"])


async def _get_owned_agent(db: AsyncSession, agent_id: uuid.UUID, user_id: str):
    agent = await agents_service.get_agent(db, agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail="not_found")
    if agent.creator_id != user_id:
        raise HTTPException(status_code=403, detail="forbidden")
    return agent


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
    agent = await agents_service.get_agent(db, agent_id)
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
    agent = await agents_service.submit_agent(db, agent)
    return _to_detail(agent)


@router.post("/{agent_id}/chat", response_model=ChatResponse)
async def chat_with_agent(
    agent_id: uuid.UUID,
    payload: ChatRequest,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    agent = await _get_owned_agent(db, agent_id, user_id)
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
