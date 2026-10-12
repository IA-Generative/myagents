"""Veilles (chantier 3) : `/api/v2/schedules` — créer, lire, modifier, forcer une exécution, lire
les résultats, supprimer (purge), exporter. Finalité affichée à chaque lecture."""

from __future__ import annotations

import json
import uuid

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps_v2 import exiger_portee, limiter
from app.core.config import get_settings
from app.core.portees import Operation
from app.core.security import AuthUser
from app.db.session import get_db
from app.schemas.veille import ScheduleCreate, SchedulePatch
from app.services import veilles
from app.veilles.planification import PRESETS

router = APIRouter(prefix="/schedules", tags=["veilles"])
_lecteur = exiger_portee(Operation.LISTER)
_auteur = exiger_portee(Operation.REDIGER)


@router.get("", summary="Mes veilles")
async def lister(
    user: AuthUser = Depends(_lecteur), db: AsyncSession = Depends(get_db)
):
    """La finalité est rendue avec la liste ; seules les veilles de la personne."""
    return {
        "schedules": [veilles.forme(s) for s in await veilles.lister(db, user.user_id)],
        "finalite": veilles.finalite(),
        "conservation_jours": get_settings().veille_conservation_jours,
        "presets": PRESETS,
        # Liste d'autorisation visible de la personne : les domaines consultés, par source.
        "sources": {
            "legifrance": ["www.legifrance.gouv.fr"],
            "web": list(get_settings().veille_domaines_autorises),
        },
    }


@router.get("/export", summary="Exporter mes veilles et leurs résultats")
async def exporter(
    user: AuthUser = Depends(_lecteur), db: AsyncSession = Depends(get_db)
):
    corps = await veilles.exporter(db, user.user_id)
    return Response(
        json.dumps(corps, ensure_ascii=False, indent=2),
        media_type="application/json",
        headers={"Content-Disposition": 'attachment; filename="mes-veilles.json"'},
    )


@router.post("", status_code=201, summary="Créer une veille")
async def creer(
    payload: ScheduleCreate,
    user: AuthUser = Depends(_auteur),
    db: AsyncSession = Depends(get_db),
):
    """Sujet, sources (legifrance, web), fréquence (cron ou préréglage). Le sujet passe la garde des noms."""
    return veilles.forme(await veilles.creer(db, user, payload))


@router.get("/{schedule_id}", summary="Lire une veille")
async def lire(
    schedule_id: uuid.UUID,
    user: AuthUser = Depends(_lecteur),
    db: AsyncSession = Depends(get_db),
):
    return veilles.forme(await veilles.obtenir(db, schedule_id, user.user_id))


@router.patch("/{schedule_id}", summary="Modifier une veille")
async def modifier(
    schedule_id: uuid.UUID,
    patch: SchedulePatch,
    user: AuthUser = Depends(_auteur),
    db: AsyncSession = Depends(get_db),
):
    s = await veilles.obtenir(db, schedule_id, user.user_id)
    return veilles.forme(await veilles.modifier(db, s, patch))


@router.delete("/{schedule_id}", summary="Supprimer une veille et purger ses résultats")
async def supprimer(
    schedule_id: uuid.UUID,
    user: AuthUser = Depends(_auteur),
    db: AsyncSession = Depends(get_db),
):
    s = await veilles.obtenir(db, schedule_id, user.user_id)
    return {"deleted": True, "results_purged": await veilles.supprimer(db, s)}


@router.post("/{schedule_id}/run", summary="Forcer une exécution maintenant")
async def forcer(
    schedule_id: uuid.UUID,
    user: AuthUser = Depends(_auteur),
    db: AsyncSession = Depends(get_db),
):
    """Une exécution par veille et par minute ; une seconde demande rend le même résultat."""
    from datetime import UTC, datetime

    s = await veilles.obtenir(db, schedule_id, user.user_id)
    limiter(user)
    status, result_id = await veilles.executer(
        db, s, datetime.now(UTC), route="cron:force"
    )
    return {"status": status, "result_id": str(result_id) if result_id else None}


@router.get("/{schedule_id}/results", summary="Résultats d'une veille")
async def resultats(
    schedule_id: uuid.UUID,
    user: AuthUser = Depends(_lecteur),
    db: AsyncSession = Depends(get_db),
):
    """Synthèses marquées « générées », sources citées (titre, lien, date, extrait court), URL consultées."""
    s = await veilles.obtenir(db, schedule_id, user.user_id)
    return {
        "results": [veilles.forme_resultat(r) for r in await veilles.resultats(db, s)]
    }
