"""Routes for rating community agents."""

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user_id
from app.db.session import get_db
from app.schemas.agent import RatingCreate, RatingRead
from app.services import agents as agents_service
from app.services import ratings as ratings_service

router = APIRouter(prefix="/ratings", tags=["ratings"])


async def _require_accessible(db: AsyncSession, agent_id: uuid.UUID, user_id: str):
    if await agents_service.get_accessible_agent(db, agent_id, user_id) is None:
        raise HTTPException(status_code=404, detail="not_found")


@router.post("/{agent_id}", response_model=RatingRead)
async def rate_agent(
    agent_id: uuid.UUID,
    payload: RatingCreate,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    await _require_accessible(db, agent_id, user_id)
    return await ratings_service.rate_agent(
        db, agent_id, user_id, payload.score, payload.comment
    )


@router.get("/{agent_id}", response_model=list[RatingRead])
async def list_ratings(
    agent_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    await _require_accessible(db, agent_id, user_id)
    return await ratings_service.list_ratings(db, agent_id)
