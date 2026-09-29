"""Routes for favoriting community agents."""

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user_id
from app.db.session import get_db
from app.schemas.agent import FavoriteRead
from app.services import favorites as favorites_service

router = APIRouter(prefix="/favorites", tags=["favorites"])


@router.get("", response_model=list[FavoriteRead])
async def list_favorites(
    db: AsyncSession = Depends(get_db), user_id: str = Depends(get_current_user_id)
):
    return await favorites_service.list_favorites(db, user_id)


@router.post("/{agent_id}", response_model=FavoriteRead)
async def add_favorite(
    agent_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    return await favorites_service.add_favorite(db, agent_id, user_id)


@router.delete("/{agent_id}")
async def remove_favorite(
    agent_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    await favorites_service.remove_favorite(db, agent_id, user_id)
    return {"agent_id": str(agent_id), "removed": True}
