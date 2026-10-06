"""Le jeu d'essai du contrat est idempotent et donne exactement ce que sa docstring promet."""

from app.scripts.seed_contrat import (
    AGENTS,
    CREATOR_ID,
    GROUPE_TESTEURS,
    seed_contrat_agents,
)
from app.services import agents as agents_service


async def test_seed_idempotent_et_visibilite_attendue(db_session):
    assert await seed_contrat_agents(db_session) == len(AGENTS)
    assert await seed_contrat_agents(db_session) == 0

    vus = await agents_service.list_accessible(db_session, "testeur", [GROUPE_TESTEURS])
    noms = sorted(agents_service.current_config(a).name for a in vus)
    assert noms == [
        "Préparateur de réunion",
        "Relecteur de courriels",
        "Synthèse pour la direction",
    ]
    assert all(a.creator_id == CREATOR_ID for a in vus)

    hors_groupe = await agents_service.list_accessible(db_session, "testeur", ["/g/rh"])
    assert sorted(agents_service.current_config(a).name for a in hors_groupe) == [
        "Relecteur de courriels",
        "Synthèse pour la direction",
    ]
