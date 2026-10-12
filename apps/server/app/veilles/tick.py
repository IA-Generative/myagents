"""Le battement des veilles : exécute les créneaux dus (au plus trois de rattrapage par veille),
une fois chacun, puis purge les résultats expirés. Appelé par le CronJob (`python -m
app.scripts.veilles_tick`) ; sans ordonnanceur en mémoire (un seul réplica ne suffirait pas à le
rendre sûr)."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.veille import Schedule
from app.services import veilles
from app.veilles.planification import CronInvalide, analyser, creneaux_dus

logger = logging.getLogger(__name__)


async def tick(
    db: AsyncSession,
    *,
    maintenant: datetime | None = None,
    depuis: datetime | None = None,
    rattrapage: int = 3,
) -> dict:
    maintenant = maintenant or datetime.now(UTC)
    bilan = {"executees": 0, "ignorees": 0, "erreurs": 0, "purges": 0}
    actives = list(
        (await db.execute(select(Schedule).where(Schedule.actif.is_(True))))
        .scalars()
        .all()
    )
    for s in actives:
        try:
            cron = analyser(s.cron)
        except CronInvalide:
            logger.warning("[veilles] cron invalide sur %s, ignorée", s.id)
            continue
        base = s.derniere_execution or depuis or (maintenant - timedelta(hours=1))
        if base.tzinfo is None:
            base = base.replace(tzinfo=UTC)
        for slot in creneaux_dus(cron, base, maintenant, maximum=rattrapage):
            status, _ = await veilles.executer(db, s, slot, route="cron")
            if status == "ok":
                bilan["executees"] += 1
            elif status == "deja_executee":
                bilan["ignorees"] += 1
            else:
                bilan["erreurs"] += 1
    bilan["purges"] = await veilles.purger_expires(db, maintenant)
    return bilan
