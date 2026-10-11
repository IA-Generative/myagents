"""Veilles (chantier 3) : création gouvernée (garde des sujets), exécution par un compte technique
de collecte, résultat déposé dans l'espace de la personne, purge et export."""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.contrat import ContratError
from app.core.security import AuthUser
from app.models.veille import Schedule, ScheduleRun, VeilleResultat
from app.schemas.veille import ScheduleCreate, SchedulePatch
from app.veilles import collecte, garde_noms
from app.veilles.planification import PRESETS, CronInvalide, analyser

logger = logging.getLogger(__name__)

CAPACITE_VEILLE = "veille.synthese"
COMPTE_TECHNIQUE = AuthUser(
    user_id="service:veilles",
    username="service:veilles",
    email="",
    roles=[],
    groups=[],
    is_admin=False,
    azp="mes-agents-cron",
    scopes=("mesagents:read",),
)


def finalite() -> str:
    jours = get_settings().veille_conservation_jours
    return (
        "Cette veille vous est personnelle : son sujet, ses sources, sa fréquence et ses résultats "
        "ne servent qu'à vous signaler les publications sur ce sujet. La collecte se fait avec un "
        "compte technique, en lecture seule, sur des sources publiques autorisées ; rien n'est fait "
        f"en votre nom. Les résultats sont effacés après {jours} jours ; supprimer la veille efface "
        "tout, en un geste ; vous pouvez exporter vos veilles à tout moment."
    )


def _cron_normalise(expression: str) -> str:
    texte = (expression or "").strip().lower()
    texte = PRESETS.get(texte, texte)
    try:
        analyser(texte)
    except CronInvalide as exc:
        raise ContratError(
            400, "invalid_request", f"fréquence invalide : {exc}"
        ) from exc
    return texte


def forme(s: Schedule) -> dict[str, Any]:
    return {
        "id": str(s.id),
        "sujet": s.sujet,
        "sources": s.sources,
        "cron": s.cron,
        "actif": s.actif,
        "conservation_jours": s.conservation_jours,
        "derniere_execution": s.derniere_execution.isoformat()
        if s.derniere_execution
        else None,
        "created_at": s.created_at.isoformat() if s.created_at else None,
        "updated_at": s.updated_at.isoformat() if s.updated_at else None,
        "finalite": finalite(),
    }


def forme_resultat(r: VeilleResultat) -> dict[str, Any]:
    return {
        "id": str(r.id),
        "created_at": r.created_at.isoformat() if r.created_at else None,
        "expires_at": r.expires_at.isoformat() if r.expires_at else None,
        "synthese": r.synthese,
        "generated": r.generated,
        "sources": r.sources,
        "urls_consultees": r.urls_consultees,
        "run_id": str(r.run_id) if r.run_id else None,
    }


async def lister(db: AsyncSession, sub: str) -> list[Schedule]:
    stmt = select(Schedule).where(Schedule.sub == sub).order_by(Schedule.created_at)
    return list((await db.execute(stmt)).scalars().all())


async def obtenir(db: AsyncSession, schedule_id: uuid.UUID, sub: str) -> Schedule:
    s = await db.get(Schedule, schedule_id)
    if s is None or s.sub != sub:
        raise ContratError.de("not_found", "veille introuvable")
    return s


async def _verifier_sujet(sujet: str) -> None:
    verdict = await garde_noms.verifier_sujet(sujet)
    if not verdict.admis:
        raise ContratError(
            422,
            "guard_rejected",
            "le sujet de la veille est refusé",
            details=[verdict.raison],
        )


async def creer(db: AsyncSession, user: AuthUser, payload: ScheduleCreate) -> Schedule:
    cron = _cron_normalise(payload.cron)
    await _verifier_sujet(payload.sujet)
    s = Schedule(
        sub=user.user_id,
        capability_name=CAPACITE_VEILLE,
        sujet=payload.sujet.strip(),
        sources=sorted(set(payload.sources)),
        cron=cron,
        actif=payload.actif,
        conservation_jours=get_settings().veille_conservation_jours,
    )
    db.add(s)
    await db.commit()
    await db.refresh(s)
    return s


async def modifier(db: AsyncSession, s: Schedule, patch: SchedulePatch) -> Schedule:
    champs = patch.model_dump(exclude_unset=True)
    if "cron" in champs and champs["cron"] is not None:
        champs["cron"] = _cron_normalise(champs["cron"])
    if "sujet" in champs and champs["sujet"] is not None:
        await _verifier_sujet(champs["sujet"])
        champs["sujet"] = champs["sujet"].strip()
    if "sources" in champs and champs["sources"] is not None:
        champs["sources"] = sorted(set(champs["sources"]))
    for nom, valeur in champs.items():
        if valeur is not None:
            setattr(s, nom, valeur)
    await db.commit()
    await db.refresh(s)
    return s


async def supprimer(db: AsyncSession, s: Schedule) -> int:
    """Supprime la veille, ses créneaux et ses résultats (purge) ; rend le nombre de résultats effacés."""
    resultats = list(
        (
            await db.execute(
                select(VeilleResultat.id).where(VeilleResultat.schedule_id == s.id)
            )
        )
        .scalars()
        .all()
    )
    await db.execute(delete(VeilleResultat).where(VeilleResultat.schedule_id == s.id))
    await db.execute(delete(ScheduleRun).where(ScheduleRun.schedule_id == s.id))
    await db.delete(s)
    await db.commit()
    return len(resultats)


async def resultats(db: AsyncSession, s: Schedule) -> list[VeilleResultat]:
    stmt = (
        select(VeilleResultat)
        .where(VeilleResultat.schedule_id == s.id)
        .order_by(VeilleResultat.created_at.desc())
    )
    return list((await db.execute(stmt)).scalars().all())


async def executer(
    db: AsyncSession, s: Schedule, slot: datetime, *, route: str = "cron"
) -> tuple[str, uuid.UUID | None]:
    """Exécute la veille sur un créneau ; (« deja_executee », résultat) si le créneau a déjà été joué."""
    from app.services.execution import ContexteAppel
    from app.services.execution import executer as executer_capacite

    slot = slot.replace(second=0, microsecond=0)
    schedule_id = s.id
    run = ScheduleRun(schedule_id=schedule_id, slot=slot, status="en_cours")
    db.add(run)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        await db.refresh(s)
        # Comparaison en Python sur la minute : SQLite range les dates en texte, sans fuseau.
        runs = (
            (
                await db.execute(
                    select(ScheduleRun).where(ScheduleRun.schedule_id == schedule_id)
                )
            )
            .scalars()
            .all()
        )
        existant = next(
            (
                r
                for r in runs
                if r.slot.replace(tzinfo=None) == slot.replace(tzinfo=None)
            ),
            None,
        )
        return "deja_executee", existant.result_id if existant else None

    ctx = ContexteAppel(user=COMPTE_TECHNIQUE, jeton=None, route=route)
    jeton_urls = collecte.urls_consultees.set([])
    jeton_fiches = collecte.fiches_collectees.set([])
    try:
        resultat = await executer_capacite(
            db,
            ctx,
            s.capability_name,
            None,
            {
                "sujet": s.sujet,
                "sources": list(s.sources),
                "seeds": list(get_settings().veille_seeds),
            },
        )
        urls = list(collecte.urls_consultees.get() or [])
        fiches = collecte.fiches_collectees.get() or []
    finally:
        collecte.urls_consultees.reset(jeton_urls)
        collecte.fiches_collectees.reset(jeton_fiches)

    run_id = uuid.UUID(resultat.meta["run_id"]) if resultat.meta.get("run_id") else None
    if resultat.is_error:
        run.status = f"erreur:{resultat.code}"[:24]
        run.run_id = run_id
        await db.commit()
        return run.status, None

    vues: set[str] = set()
    sources = []
    for f in fiches:
        if f.get("url") in vues:
            continue
        vues.add(f.get("url"))
        sources.append(
            {k: f.get(k, "") for k in ("title", "url", "date", "author", "extrait")}
        )
    maintenant = datetime.now(UTC)
    r = VeilleResultat(
        id=uuid.uuid4(),  # posé ici : l'identifiant est référencé avant le flush
        schedule_id=s.id,
        sub=s.sub,
        synthese=resultat.texte,
        generated=True,
        sources=sources,
        urls_consultees=urls,
        run_id=run_id,
        created_at=maintenant,
        expires_at=maintenant
        + timedelta(
            days=s.conservation_jours or get_settings().veille_conservation_jours
        ),
    )
    db.add(r)
    run.status = "ok"
    run.result_id = r.id
    run.run_id = run_id
    s.derniere_execution = slot
    await db.commit()
    return "ok", r.id


async def purger_expires(db: AsyncSession, maintenant: datetime) -> int:
    ids = list(
        (
            await db.execute(
                select(VeilleResultat.id).where(VeilleResultat.expires_at < maintenant)
            )
        )
        .scalars()
        .all()
    )
    if ids:
        await db.execute(delete(VeilleResultat).where(VeilleResultat.id.in_(ids)))
        await db.commit()
    return len(ids)


async def exporter(db: AsyncSession, sub: str) -> dict[str, Any]:
    veilles = []
    for s in await lister(db, sub):
        veilles.append(
            {**forme(s), "results": [forme_resultat(r) for r in await resultats(db, s)]}
        )
    return {
        "sub": sub,
        "exported_at": datetime.now(UTC).isoformat(),
        "finalite": finalite(),
        "schedules": veilles,
    }
