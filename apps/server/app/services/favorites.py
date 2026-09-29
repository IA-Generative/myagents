"""Business logic for agent favorites."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent import Favorite


async def add_favorite(db: AsyncSession, agent_id: uuid.UUID, user_id: str) -> Favorite:
    existing = (
        await db.execute(
            select(Favorite).where(
                Favorite.agent_id == agent_id, Favorite.user_id == user_id
            )
        )
    ).scalar_one_or_none()
    if existing:
        return existing

    favorite = Favorite(agent_id=agent_id, user_id=user_id)
    db.add(favorite)
    await db.commit()
    await db.refresh(favorite)
    return favorite


async def remove_favorite(db: AsyncSession, agent_id: uuid.UUID, user_id: str) -> None:
    existing = (
        await db.execute(
            select(Favorite).where(
                Favorite.agent_id == agent_id, Favorite.user_id == user_id
            )
        )
    ).scalar_one_or_none()
    if existing:
        await db.delete(existing)
        await db.commit()


async def list_favorites(db: AsyncSession, user_id: str) -> list[Favorite]:
    stmt = select(Favorite).where(Favorite.user_id == user_id)
    return list((await db.execute(stmt)).scalars().all())
