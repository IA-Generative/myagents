"""API de cycle de vie des capacités (ADR §4.5, §10.1 point 3) sous /api/v2.

Six opérations (créer, modifier, tester, publier, retirer, journal) plus la lecture pour les
écrans. Toute erreur est `{"error": {"code", "message"[, "details"]}}` (§10.0).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import PlainTextResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps_v2 import exiger_portee, get_v2_user, limiter
from app.core.config import get_settings
from app.core.contrat import ContratError
from app.core.portees import Operation, exiger
from app.core.security import AuthUser
from app.db.session import get_db
from app.mcp import filtrage
from app.schemas.capability import (
    CapabilityCreate,
    CapabilityPatch,
    PublishRequest,
    TestRequest,
)
from app.services import capabilities as service
from app.services import journal, pins
from app.services.execution import ContexteAppel, tester_brouillon

router = APIRouter(prefix="/capabilities", tags=["capacites"])

_lecteur = exiger_portee(Operation.LISTER)
_auteur = exiger_portee(Operation.REDIGER)


async def _capacite_visible(db: AsyncSession, cap_id: uuid.UUID, user: AuthUser):
    cap = await service.obtenir(db, cap_id)
    if cap is None or not await service.visible(db, cap, user):
        raise ContratError.de("not_found")
    return cap


async def _capacite_de_l_auteur(db: AsyncSession, cap_id: uuid.UUID, user: AuthUser):
    cap = await service.obtenir(db, cap_id)
    if cap is None or cap.owner_sub != user.user_id:
        raise ContratError.de("not_found")
    return cap


async def _detail(db: AsyncSession, cap, user: AuthUser) -> dict:
    version = await service.version_servie(db, cap)
    epingles = await pins.noms(db, user.user_id)
    return service.detail(cap, version, user, epinglee=cap.name in epingles)


@router.get("", summary="Lister les capacités visibles (même forme que tools/list)")
async def lister(
    context: str | None = Query(
        default=None,
        description="Filtrer selon les champs qu'une surface (azp) sait fournir",
    ),
    user: AuthUser = Depends(_lecteur),
    db: AsyncSession = Depends(get_db),
):
    """Les capacités que la personne peut voir : les siennes (brouillons compris) et celles servies pour elle."""
    epingles = set(await pins.noms(db, user.user_id))
    champs = (
        filtrage.champs_fournis(context, get_settings().mesagents_contextes_azp)
        if context
        else None
    )
    outils = []
    for cap in await service.lister_visibles(db, user):
        version = service.version_numero(cap, cap.current_version)
        if champs is not None and not filtrage.servie_au_contexte(
            (version or cap).input_schema or {}, champs
        ):
            continue
        outils.append(
            service.forme_gestion(cap, version, epinglee=cap.name in epingles)
        )
    return {"tools": outils, "pins_max": get_settings().mesagents_epingles_max}


@router.post("", status_code=201, summary="Créer un brouillon")
async def creer(
    payload: CapabilityCreate,
    user: AuthUser = Depends(_auteur),
    db: AsyncSession = Depends(get_db),
):
    """`kind`, `definition`, schémas, dépendances, `grounding`, visibilité, exemples. Les champs posés par le service sont ignorés."""
    cap = await service.creer(db, user, payload)
    return await _detail(db, cap, user)


@router.get("/{cap_id}", summary="Lire une capacité")
async def lire(
    cap_id: uuid.UUID,
    user: AuthUser = Depends(_lecteur),
    db: AsyncSession = Depends(get_db),
):
    """Fiche, versions et provenance ; la définition n'est rendue qu'à l'auteur et aux relecteurs."""
    cap = await _capacite_visible(db, cap_id, user)
    return await _detail(db, cap, user)


@router.patch("/{cap_id}", summary="Modifier un brouillon")
async def modifier(
    cap_id: uuid.UUID,
    patch: CapabilityPatch,
    user: AuthUser = Depends(_auteur),
    db: AsyncSession = Depends(get_db),
):
    """Brouillon seulement : une capacité publiée répond `409 immutable_version` (ouvrez un brouillon)."""
    cap = await _capacite_de_l_auteur(db, cap_id, user)
    cap = await service.modifier(db, cap, patch)
    return await _detail(db, cap, user)


@router.post("/{cap_id}/draft", summary="Ouvrir un brouillon sur une capacité publiée")
async def ouvrir_brouillon(
    cap_id: uuid.UUID,
    user: AuthUser = Depends(_auteur),
    db: AsyncSession = Depends(get_db),
):
    """La version publiée reste servie ; la publication suivante créera la version n+1."""
    cap = await _capacite_de_l_auteur(db, cap_id, user)
    cap = await service.ouvrir_brouillon(db, cap)
    return await _detail(db, cap, user)


@router.post("/{cap_id}/test", summary="Tester le brouillon")
async def tester(
    cap_id: uuid.UUID,
    demande: TestRequest,
    request: Request,
    user: AuthUser = Depends(_auteur),
    db: AsyncSession = Depends(get_db),
):
    """Exécute le brouillon pour l'auteur et rend le résultat ET le verdict de garde sur la définition."""
    cap = await _capacite_de_l_auteur(db, cap_id, user)
    limiter(user)
    ctx = ContexteAppel(
        user=user, jeton=getattr(request.state, "jeton", None), route="api.test"
    )
    return await tester_brouillon(db, ctx, cap, demande.arguments)


@router.post("/{cap_id}/publish", summary="Publier")
async def publier(
    cap_id: uuid.UUID,
    demande: PublishRequest,
    user: AuthUser = Depends(get_v2_user),
    db: AsyncSession = Depends(get_db),
):
    """Ordre : droit de la personne, portée du client, verdict de garde, règle de dépendance, puis version + hash. `ministry` ou non lecture seule : revue."""
    cap = await service.obtenir(db, cap_id)
    if cap is None:
        raise ContratError.de("not_found")
    if cap.owner_sub != user.user_id and cap.status != "submitted":
        raise ContratError.de("not_found")
    cap = await service.publier(db, user, cap, demande)
    return await _detail(db, cap, user)


@router.post("/{cap_id}/retire", summary="Retirer")
async def retirer(
    cap_id: uuid.UUID,
    user: AuthUser = Depends(get_v2_user),
    db: AsyncSession = Depends(get_db),
):
    """Retire la version servie ; les capacités qui en dépendent passent à `suspended` et sont notifiées."""
    cap = await _capacite_visible(db, cap_id, user)
    if cap.owner_sub != user.user_id and "mesagents:review" not in user.scopes:
        exiger(user.scopes, Operation.REVOIR)
    cap = await service.retirer(db, user, cap)
    return await _detail(db, cap, user)


@router.get(
    "/{cap_id}/runs", summary="Journal des exécutions", response_class=PlainTextResponse
)
async def journal_runs(
    cap_id: uuid.UUID,
    since: datetime | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=1000),
    user: AuthUser = Depends(_lecteur),
    db: AsyncSession = Depends(get_db),
):
    """JSON Lines : une ligne par appel (ts, capability, version, hash, sub, azp, scope_used, guard_in, guard_out, duration_ms, status). Auteur, ou relecteur."""
    cap = await service.obtenir(db, cap_id)
    if cap is None or (
        cap.owner_sub != user.user_id
        and not (user.is_reviewer and "mesagents:review" in user.scopes)
    ):
        raise ContratError.de("not_found")
    lignes = await journal.lister(db, capability_id=cap.id, since=since, limit=limit)
    return PlainTextResponse(
        journal.exporter(lignes), media_type="application/x-ndjson"
    )
