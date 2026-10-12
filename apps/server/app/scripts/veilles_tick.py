"""CronJob des veilles : `python -m app.scripts.veilles_tick` (toutes les quinze minutes en preview).

Joue les créneaux dus de chaque veille active — une fois chacun, avec au plus trois créneaux de
rattrapage — puis purge les résultats expirés. Rien n'est fait au nom d'une personne : la collecte
tourne avec le compte technique `service:veilles` et dépose le résultat dans l'espace de la personne.
"""

import asyncio
import json
import logging

from app.core.logging import setup_logging
from app.db.session import SessionLocal
from app.veilles.tick import tick


async def _main() -> None:
    async with SessionLocal() as db:
        bilan = await tick(db)
    logging.getLogger(__name__).info("[veilles] battement : %s", json.dumps(bilan))


if __name__ == "__main__":
    setup_logging()
    asyncio.run(_main())
