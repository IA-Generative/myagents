"""Business logic for agent ratings."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent import Rating


async def rate_agent(
    db: AsyncSession, agent_id: uuid.UUID, user_id: str, score: int, comment: str | None
) -> Rating:
    existing = (
        await db.execute(
            select(Rating).where(Rating.agent_id == agent_id, Rating.user_id == user_id)
        )
    ).scalar_one_or_none()
    if existing:
        existing.score = score
        existing.comment = comment
        await db.commit()
        await db.refresh(existing)
        return existing

    rating = Rating(agent_id=agent_id, user_id=user_id, score=score, comment=comment)
    db.add(rating)
    await db.commit()
    await db.refresh(rating)
    return rating


async def list_ratings(db: AsyncSession, agent_id: uuid.UUID) -> list[Rating]:
    stmt = (
        select(Rating)
        .where(Rating.agent_id == agent_id)
        .order_by(Rating.created_at.desc())
    )
    return list((await db.execute(stmt)).scalars().all())
