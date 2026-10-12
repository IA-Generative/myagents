"""Épinglage (ADR §4.4 point 2, §10.3 point 3) : `GET /pins`, `PUT|DELETE /pins/{name}`."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps_v2 import exiger_portee
from app.core.contrat import ContratError
from app.core.portees import Operation
from app.core.security import AuthUser
from app.db.session import get_db
from app.mcp import notifications
from app.services import capabilities as service
from app.services import pins

router = APIRouter(prefix="/pins", tags=["capacites"])

_auteur = exiger_portee(Operation.REDIGER)
_lecteur = exiger_portee(Operation.LISTER)


def _reponse(noms: list[str]) -> dict:
    return {"pins": noms, "max": pins.plafond()}


@router.get("", summary="Mes capacités épinglées")
async def lister(
    user: AuthUser = Depends(_lecteur), db: AsyncSession = Depends(get_db)
):
    return _reponse(await pins.noms(db, user.user_id))


@router.put("/{name}", summary="Épingler")
async def epingler(
    name: str, user: AuthUser = Depends(_auteur), db: AsyncSession = Depends(get_db)
):
    """Au plus `max` capacités ; au-delà, `422 invalid_request`."""
    cap = await service.par_nom(db, name)
    if (
        cap is None
        or not await service.visible(db, cap, user)
        or cap.current_version is None
    ):
        raise ContratError.de("not_found")
    noms = await pins.epingler(db, user.user_id, cap)
    notifications.diffuseur.notifier_list_changed([user.user_id])
    return _reponse(noms)


@router.delete("/{name}", summary="Désépingler")
async def desepingler(
    name: str, user: AuthUser = Depends(_auteur), db: AsyncSession = Depends(get_db)
):
    cap = await service.par_nom(db, name)
    if cap is None:
        raise ContratError.de("not_found")
    noms = await pins.desepingler(db, user.user_id, cap)
    notifications.diffuseur.notifier_list_changed([user.user_id])
    return _reponse(noms)
