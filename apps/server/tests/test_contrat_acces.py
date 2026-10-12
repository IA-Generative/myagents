"""La règle d'accès unique du contrat d'agents (app.services.agents.is_accessible)."""

import pytest

from app.models.agent import Agent, AgentVersion
from app.models.enums import AgentStatus, Visibility
from app.schemas.agent import ConfigSnapshot
from app.services.agents import groupe_correspond, is_accessible

AUTEUR = "auteur"
AUTRE = "autre"


def _agent(visibility, status, community_path=None, creator=AUTEUR) -> Agent:
    agent = Agent(
        creator_id=creator, model_ref="chat", visibility=visibility, status=status
    )
    agent.versions.append(
        AgentVersion(
            version=1,
            config_snapshot=ConfigSnapshot(
                name="a", community_path=community_path
            ).model_dump(),
        )
    )
    return agent


@pytest.mark.parametrize(
    ("visibility", "status", "chemin", "groupes", "attendu"),
    [
        # L'auteur voit tout sauf l'archivé.
        (Visibility.private, AgentStatus.draft, None, [], True),
        (Visibility.ministry, AgentStatus.archived, None, [], False),
    ],
)
def test_auteur(visibility, status, chemin, groupes, attendu):
    assert is_accessible(_agent(visibility, status, chemin), AUTEUR, groupes) is attendu


@pytest.mark.parametrize(
    ("visibility", "status", "chemin", "groupes", "attendu"),
    [
        (Visibility.private, AgentStatus.published, None, [], False),
        (Visibility.ministry, AgentStatus.draft, None, [], False),
        (Visibility.ministry, AgentStatus.published, None, [], True),
        (Visibility.ministry, AgentStatus.submitted, None, [], True),
        (Visibility.ministry, AgentStatus.archived, None, [], False),
        # Communauté : chemin complet, ou nom feuille — jamais un chemin contre un nom.
        (
            Visibility.community,
            AgentStatus.published,
            "/g/juridique",
            ["/g/juridique"],
            True,
        ),
        (Visibility.community, AgentStatus.published, "/g/juridique", ["/g/rh"], False),
        (
            Visibility.community,
            AgentStatus.published,
            "/g/juridique",
            ["juridique"],
            False,
        ),
        (
            Visibility.community,
            AgentStatus.published,
            "juridique",
            ["/g/juridique"],
            True,
        ),
        (Visibility.community, AgentStatus.published, "juridique", ["juridique"], True),
        (Visibility.community, AgentStatus.published, None, ["/g/juridique"], False),
        (
            Visibility.community,
            AgentStatus.draft,
            "/g/juridique",
            ["/g/juridique"],
            False,
        ),
    ],
)
def test_tiers(visibility, status, chemin, groupes, attendu):
    assert is_accessible(_agent(visibility, status, chemin), AUTRE, groupes) is attendu


def test_groupe_correspond_tolere_la_barre_finale():
    assert groupe_correspond("/g/juridique/", ["/g/juridique"])
    assert groupe_correspond("/g/juridique", ["/g/juridique/"])
    assert not groupe_correspond("", ["/g/juridique"])
