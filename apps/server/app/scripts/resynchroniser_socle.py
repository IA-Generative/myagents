"""Repose la fiche de chaque agent dans le socle (Open WebUI), d'après la base.

À jouer après la mise en service de la connexion `/v1` du socle, ou après une reprise de
données : `python -m app.scripts.resynchroniser_socle [--a-sec]`. Une fiche qui échoue
n'arrête pas les autres ; le bilan les nomme.
"""

import asyncio
import json
import logging
import sys

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.logging import setup_logging
from app.db.session import SessionLocal
from app.models.agent import Agent
from app.services import agents as agents_service
from app.services import socle

logger = logging.getLogger(__name__)


async def resynchroniser(a_sec: bool = False) -> dict:
    async with SessionLocal() as db:
        stmt = (
            select(Agent)
            .options(selectinload(Agent.versions))
            .order_by(Agent.updated_at)
        )
        agents = list((await db.execute(stmt)).scalars().all())
    bilan: list[dict] = []
    for agent in agents:
        nom = agents_service.current_config(agent).name
        attendu = "posee" if socle.doit_avoir_une_fiche(agent) else "retiree"
        if a_sec:
            bilan.append({"id": str(agent.id), "nom": nom, "attendu": attendu})
            continue
        etat = await socle.synchroniser(agent)
        bilan.append({"id": str(agent.id), "nom": nom, "etat": etat})
    return {"a_sec": a_sec, "agents": bilan}


async def main() -> None:
    setup_logging()
    bilan = await resynchroniser(a_sec="--a-sec" in sys.argv)
    print(json.dumps(bilan, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
