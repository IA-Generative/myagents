"""Administration du contrat de capacités : export du journal, re-vérification (règle 7),
clients suspendus (ADR §4.7). Portée `mesagents:review` et rôle `mesagents-reviewer`."""

from datetime import datetime

from fastapi import APIRouter, Depends, Query
from fastapi.responses import PlainTextResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps_v2 import exiger_portee
from app.core.contrat import ContratError
from app.core.portees import Operation
from app.core.security import AuthUser
from app.db.session import get_db
from app.schemas.capability import SuspendRequest
from app.services import capability_guard, journal, suspension

router = APIRouter(prefix="/admin", tags=["administration"])


async def _administrateur(
    user: AuthUser = Depends(exiger_portee(Operation.REVOIR)),
) -> AuthUser:
    if not user.is_reviewer:
        raise ContratError(
            403, "forbidden", "l'administration exige le rôle mesagents-reviewer"
        )
    return user


@router.get("/runs", summary="Export du journal", response_class=PlainTextResponse)
async def export_runs(
    since: datetime | None = Query(default=None),
    limit: int = Query(default=1000, ge=1, le=10000),
    user: AuthUser = Depends(_administrateur),
    db: AsyncSession = Depends(get_db),
):
    """JSON Lines de toutes les exécutions (jamais de contenu)."""
    lignes = await journal.lister(db, since=since, limit=limit)
    return PlainTextResponse(
        journal.exporter(lignes), media_type="application/x-ndjson"
    )


@router.post(
    "/guard/recheck", summary="Re-vérifier toutes les versions servies (règle 7)"
)
async def recheck(
    user: AuthUser = Depends(_administrateur), db: AsyncSession = Depends(get_db)
):
    """Rejoue la garde de définition ; une version non conforme est retirée et ses dépendants suspendus."""
    return await capability_guard.recheck_all(db, user)


@router.get("/suspended-clients", summary="Clients suspendus")
async def lister_suspendus(
    user: AuthUser = Depends(_administrateur), db: AsyncSession = Depends(get_db)
):
    return {
        "clients": [
            {
                "azp": c.azp,
                "reason": c.reason,
                "suspended_by": c.suspended_by,
                "suspended_at": c.suspended_at.isoformat() if c.suspended_at else None,
            }
            for c in await suspension.lister(db)
        ]
    }


@router.put("/suspended-clients/{azp}", summary="Suspendre un client (azp)")
async def suspendre(
    azp: str,
    demande: SuspendRequest,
    user: AuthUser = Depends(_administrateur),
    db: AsyncSession = Depends(get_db),
):
    """Effet immédiat sur tous ses appels, jeton valide ou non."""
    ligne = await suspension.suspendre(db, azp, demande.reason, user.user_id)
    return {"azp": ligne.azp, "reason": ligne.reason, "suspended": True}


@router.delete("/suspended-clients/{azp}", summary="Lever la suspension")
async def lever(
    azp: str,
    user: AuthUser = Depends(_administrateur),
    db: AsyncSession = Depends(get_db),
):
    return {"azp": azp, "suspended": not await suspension.lever(db, azp)}
