"""Journal des exécutions (ADR règle 6, §10.0 Journal) : une ligne JSON par appel, jamais le contenu.

Deux supports, dans cet ordre : une ligne JSON nue sur le logger `mesagents.journal` (sortie
standard, fichier optionnel), puis une ligne `runs` en base (best-effort : un échec d'écriture
ne casse jamais la réponse). L'export rend des JSON Lines.
"""

import contextlib
import json
import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import JOURNAL_LOGGER
from app.models.capability import Run

logger = logging.getLogger(__name__)
journal_logger = logging.getLogger(JOURNAL_LOGGER)

# Champs minimaux du contrat d'abord (§10.0), puis les compléments.
CHAMPS: tuple[str, ...] = (
    "ts",
    "capability",
    "version",
    "hash",
    "sub",
    "azp",
    "scope_used",
    "guard_in",
    "guard_out",
    "duration_ms",
    "status",
    "run_id",
    "parent_run_id",
    "route",
    "ruleset_version",
    "capability_id",
)


def ligne_json(run: Run) -> str:
    valeurs = {
        "ts": run.ts.astimezone(UTC).isoformat(timespec="milliseconds")
        if run.ts
        else None,
        "capability": run.capability,
        "version": run.version,
        "hash": run.hash,
        "sub": run.sub,
        "azp": run.azp,
        "scope_used": run.scope_used,
        "guard_in": run.guard_in,
        "guard_out": run.guard_out,
        "duration_ms": run.duration_ms,
        "status": run.status,
        "run_id": str(run.id),
        "parent_run_id": str(run.parent_run_id) if run.parent_run_id else None,
        "route": run.route,
        "ruleset_version": run.ruleset_version,
        "capability_id": str(run.capability_id) if run.capability_id else None,
    }
    return json.dumps({c: valeurs[c] for c in CHAMPS}, ensure_ascii=False)


async def ecrire(
    db: AsyncSession | None,
    *,
    capability: str,
    capability_id: uuid.UUID | None,
    version: int | None,
    hash: str | None,
    sub: str,
    azp: str,
    scope_used: str,
    guard_in: str,
    guard_out: str,
    ruleset_version: str,
    duration_ms: int,
    status: str,
    route: str,
    parent_run_id: uuid.UUID | None = None,
    run_id: uuid.UUID | None = None,
) -> Run:
    run = Run(
        id=run_id or uuid.uuid4(),
        ts=datetime.now(UTC),
        capability=capability[:64],
        capability_id=capability_id,
        version=version,
        hash=hash,
        sub=sub[:255],
        azp=(azp or "")[:255],
        scope_used=scope_used[:32],
        guard_in=guard_in,
        guard_out=guard_out,
        ruleset_version=ruleset_version[:32],
        duration_ms=max(0, int(duration_ms)),
        status=status,
        route=route[:32],
        parent_run_id=parent_run_id,
    )
    journal_logger.info(ligne_json(run))
    if db is not None:
        try:
            db.add(run)
            await db.commit()
        except Exception as exc:  # noqa: BLE001 — le journal ne casse jamais la requête
            logger.error(
                "[journal] échec de persistance (non bloquant): %s", type(exc).__name__
            )
            with contextlib.suppress(Exception):
                await db.rollback()
    return run


async def lister(
    db: AsyncSession,
    *,
    capability_id: uuid.UUID | None = None,
    sub: str | None = None,
    since: datetime | None = None,
    limit: int = 100,
) -> list[Run]:
    stmt = select(Run).order_by(Run.ts.desc()).limit(limit)
    if capability_id is not None:
        stmt = stmt.where(Run.capability_id == capability_id)
    if sub is not None:
        stmt = stmt.where(Run.sub == sub)
    if since is not None:
        stmt = stmt.where(Run.ts >= since)
    lignes = list((await db.execute(stmt)).scalars().all())
    lignes.reverse()  # du plus ancien au plus récent
    return lignes


def exporter(runs: list[Run]) -> str:
    return "".join(ligne_json(r) + "\n" for r in runs)
