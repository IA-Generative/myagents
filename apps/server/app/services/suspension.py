"""Clients (`azp`) suspendus (ADR §4.7, cycle de vie d'un client, point 4) : table ∪ configuration,
lus à CHAQUE appel — un client désactivé est refusé même si son jeton est encore valide."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.capability import SuspendedClient


async def est_suspendu(db: AsyncSession, azp: str) -> bool:
    if not azp:
        return False
    if azp in get_settings().mesagents_azp_suspendus:
        return True
    ligne = await db.get(SuspendedClient, azp)
    return ligne is not None


async def lister(db: AsyncSession) -> list[SuspendedClient]:
    return list((await db.execute(select(SuspendedClient))).scalars().all())


async def suspendre(
    db: AsyncSession, azp: str, reason: str, par: str
) -> SuspendedClient:
    ligne = await db.get(SuspendedClient, azp)
    if ligne is None:
        ligne = SuspendedClient(azp=azp, reason=reason, suspended_by=par)
        db.add(ligne)
    else:
        ligne.reason = reason
        ligne.suspended_by = par
    await db.commit()
    return ligne


async def lever(db: AsyncSession, azp: str) -> bool:
    ligne = await db.get(SuspendedClient, azp)
    if ligne is None:
        return False
    await db.delete(ligne)
    await db.commit()
    return True
