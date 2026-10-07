"""Routes: list/read/delete conversations and their messages."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user_id
from app.db.session import get_db
from app.services import conversations as conv_service

router = APIRouter(tags=["conversations"])


@router.get("/conversations")
async def list_conversations(
    agent_id: uuid.UUID | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    convs = await conv_service.list_conversations(db, user_id, agent_id=agent_id)
    return [conv_service.to_conversation_read(c).model_dump() for c in convs]


@router.get("/conversations/{conv_id}")
async def get_conversation(
    conv_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    conv = await conv_service.get_conversation(db, conv_id, user_id)
    if conv is None:
        raise HTTPException(status_code=404, detail="not_found")
    return conv_service.to_conversation_read(conv).model_dump()


@router.get("/conversations/{conv_id}/messages")
async def get_messages(
    conv_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    conv = await conv_service.get_conversation(db, conv_id, user_id)
    if conv is None:
        raise HTTPException(status_code=404, detail="not_found")
    msgs = await conv_service.get_messages(db, conv_id)
    return [conv_service.to_message_read(m).model_dump() for m in msgs]


@router.delete("/conversations/{conv_id}")
async def delete_conversation(
    conv_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    conv = await conv_service.get_conversation(db, conv_id, user_id)
    if conv is None:
        raise HTTPException(status_code=404, detail="not_found")
    await conv_service.delete_conversation(db, conv)
    return {"id": str(conv_id), "status": "deleted"}
