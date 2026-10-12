"""Épinglage (ADR §4.4 point 2) : les capacités qu'une personne veut voir comme de vrais outils."""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.contrat import ContratError
from app.models.capability import Capability, Pin


def plafond() -> int:
    return get_settings().mesagents_epingles_max


async def lister(db: AsyncSession, sub: str) -> list[Capability]:
    stmt = (
        select(Capability)
        .join(Pin, Pin.capability_id == Capability.id)
        .where(Pin.sub == sub)
        .order_by(Pin.rang)
    )
    return list((await db.execute(stmt)).scalars().all())


async def noms(db: AsyncSession, sub: str) -> list[str]:
    return [c.name for c in await lister(db, sub)]


async def epingler(db: AsyncSession, sub: str, cap: Capability) -> list[str]:
    existante = (
        await db.execute(select(Pin).where(Pin.sub == sub, Pin.capability_id == cap.id))
    ).scalar_one_or_none()
    if existante is None:
        nombre = (
            await db.execute(
                select(func.count()).select_from(Pin).where(Pin.sub == sub)
            )
        ).scalar_one()
        if nombre >= plafond():
            raise ContratError(
                422,
                "invalid_request",
                f"plafond d'épinglage atteint ({plafond()}) : désépinglez une capacité d'abord",
            )
        rang = (
            await db.execute(select(func.max(Pin.rang)).where(Pin.sub == sub))
        ).scalar_one() or 0
        db.add(Pin(sub=sub, capability_id=cap.id, rang=rang + 1))
        await db.commit()
    return await noms(db, sub)


async def desepingler(db: AsyncSession, sub: str, cap: Capability) -> list[str]:
    existante = (
        await db.execute(select(Pin).where(Pin.sub == sub, Pin.capability_id == cap.id))
    ).scalar_one_or_none()
    if existante is not None:
        await db.delete(existante)
        await db.commit()
    return await noms(db, sub)


async def abonnes_de(db: AsyncSession, cap: Capability) -> list[str]:
    """Les personnes qui ont épinglé la capacité (à prévenir d'un changement)."""
    stmt = select(Pin.sub).where(Pin.capability_id == cap.id)
    return list((await db.execute(stmt)).scalars().all())
