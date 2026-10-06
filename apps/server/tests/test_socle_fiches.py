"""Les fiches des agents dans le socle : ce qui est posé, pour qui, et quand c'est retiré."""

import json

import httpx
import pytest

from app.core.config import get_settings
from app.models.agent import Agent, AgentVersion
from app.models.enums import AgentStatus, Visibility
from app.schemas.agent import ConfigSnapshot
from app.services import socle

GROUPES = [
    {"id": "g-testeurs", "name": "mirai-beta-testeurs"},
    {"id": "g-rh", "name": "rh"},
]


class FauxSocle:
    """Un socle 0.11 simulé : fiches en mémoire, journal des appels."""

    def __init__(self, fiches=None, groupes=GROUPES, cle="cle-admin"):
        self.fiches = dict(fiches or {})
        self.groupes = groupes
        self.cle = cle
        self.appels: list[tuple[str, str]] = []

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self.handler)

    def handler(self, req: httpx.Request) -> httpx.Response:
        self.appels.append((req.method, req.url.path))
        if req.headers.get("authorization") != f"Bearer {self.cle}":
            return httpx.Response(401, json={"detail": "Unauthorized"})
        path = req.url.path
        if path == "/api/v1/groups/":
            return httpx.Response(200, json=self.groupes)
        if path == "/api/v1/models/model":
            fiche = self.fiches.get(req.url.params.get("id"))
            return httpx.Response(200, json=fiche) if fiche else httpx.Response(401)
        if path == "/api/v1/models/model/update":
            body = json.loads(req.content)
            if body.get("access_grants") is None:
                return httpx.Response(500, text="")
            if req.url.params.get("id") not in self.fiches:
                return httpx.Response(401, json={"detail": "not found"})
            self.fiches[body["id"]] = body
            return httpx.Response(200, json=body)
        if path == "/api/v1/models/create":
            body = json.loads(req.content)
            if body["id"] in self.fiches:
                return httpx.Response(401, json={"detail": "already registered"})
            self.fiches[body["id"]] = body
            return httpx.Response(200, json=body)
        if path == "/api/v1/models/model/delete":
            self.fiches.pop(req.url.params.get("id"), None)
            return httpx.Response(200, json=True)
        return httpx.Response(404)


def _agent(visibility, status, community_path=None, **config) -> Agent:
    agent = Agent(
        creator_id="auteur",
        model_ref="chat",
        visibility=visibility,
        status=status,
        category=["redaction"],
    )
    agent.versions.append(
        AgentVersion(
            version=1,
            config_snapshot=ConfigSnapshot(
                name="Relecteur",
                description="Relit.",
                community_path=community_path,
                examples=["Relis ceci."],
                **config,
            ).model_dump(),
        )
    )
    return agent


@pytest.fixture
def faux():
    return FauxSocle()


def _client(faux: FauxSocle) -> socle.SocleClient:
    return socle.SocleClient(
        base_url="http://socle", api_key="cle-admin", transport=faux.transport()
    )


async def test_ministere_pose_une_fiche_pour_tout_compte_connecte(faux):
    agent = _agent(Visibility.ministry, AgentStatus.published)
    assert await socle.synchroniser(agent, _client(faux)) == "posee"
    fiche = faux.fiches[str(agent.id)]
    assert fiche["access_grants"] == [
        {"principal_type": "user", "principal_id": "*", "permission": "read"}
    ]
    assert fiche["base_model_id"] is None
    assert fiche["name"] == "Relecteur"
    assert {t["name"] for t in fiche["meta"]["tags"]} == {"redaction", "Mes agents"}
    assert fiche["meta"]["suggestion_prompts"] == [{"content": "Relis ceci."}]
    assert fiche["params"] == {}


async def test_communaute_vise_le_groupe_du_socle_par_son_nom_feuille(faux):
    agent = _agent(
        Visibility.community,
        AgentStatus.published,
        community_path="/g/mirai-beta-testeurs",
    )
    assert await socle.synchroniser(agent, _client(faux)) == "posee"
    fiche = faux.fiches[str(agent.id)]
    assert fiche["access_grants"] == [
        {"principal_type": "group", "principal_id": "g-testeurs", "permission": "read"}
    ]
    assert fiche["access_control"]["read"]["group_ids"] == ["g-testeurs"]


async def test_communaute_sans_groupe_connu_ne_pose_rien(faux):
    agent = _agent(
        Visibility.community, AgentStatus.published, community_path="/g/dlpaj"
    )
    etat = await socle.synchroniser(agent, _client(faux))
    assert etat == "groupe_inconnu:dlpaj"
    assert str(agent.id) not in faux.fiches


@pytest.mark.parametrize(
    ("visibility", "status"),
    [
        (Visibility.private, AgentStatus.published),
        (Visibility.ministry, AgentStatus.draft),
        (Visibility.ministry, AgentStatus.archived),
    ],
)
async def test_prive_brouillon_archive_retirent_la_fiche(faux, visibility, status):
    agent = _agent(visibility, status)
    faux.fiches[str(agent.id)] = {"id": str(agent.id)}
    assert await socle.synchroniser(agent, _client(faux)) == "retiree"
    assert str(agent.id) not in faux.fiches


async def test_republier_met_a_jour_sans_effacer_ce_que_le_socle_a_regle(faux):
    agent = _agent(Visibility.ministry, AgentStatus.published)
    faux.fiches[str(agent.id)] = {
        "id": str(agent.id),
        "name": "Ancien nom",
        "meta": {
            "profile_image_url": "/custom.png",
            "tags": [{"name": "posée ailleurs"}, {"name": "Mes agents"}],
            "toolIds": ["web_search"],
        },
        "params": {"temperature": 0.1},
        "access_grants": [],
    }
    assert await socle.synchroniser(agent, _client(faux)) == "posee"
    fiche = faux.fiches[str(agent.id)]
    assert fiche["name"] == "Relecteur"
    assert fiche["meta"]["profile_image_url"] == "/custom.png"
    assert fiche["meta"]["toolIds"] == ["web_search"]
    assert fiche["params"] == {"temperature": 0.1}
    assert [t["name"] for t in fiche["meta"]["tags"]] == [
        "posée ailleurs",
        "redaction",
        "Mes agents",
    ]
    assert ("POST", "/api/v1/models/model/update") in faux.appels
    assert ("POST", "/api/v1/models/create") not in faux.appels


async def test_socle_non_configure_rend_indisponible(monkeypatch):
    monkeypatch.setattr(get_settings(), "owui_base_url", "")
    agent = _agent(Visibility.ministry, AgentStatus.published)
    assert await socle.synchroniser(agent) == "indisponible"


async def test_cle_refusee_rend_une_erreur_sans_lever(faux):
    agent = _agent(Visibility.ministry, AgentStatus.published)
    client = socle.SocleClient(
        base_url="http://socle", api_key="mauvaise", transport=faux.transport()
    )
    assert (await socle.synchroniser(agent, client)).startswith("erreur:")


async def test_la_route_de_creation_rend_l_etat_de_la_fiche(client, faux, monkeypatch):
    monkeypatch.setattr(socle, "_nouveau_client", lambda: _client(faux))
    res = await client.post(
        "/api/agents",
        json={
            "visibility": "ministry",
            "status": "published",
            "config": {"name": "Relecteur", "system_prompt": "Tu relis."},
        },
    )
    assert res.status_code == 200, res.text
    assert res.json()["socle"] == "posee"
    assert res.json()["id"] in faux.fiches

    brouillon = await client.post(
        "/api/agents",
        json={"config": {"name": "Brouillon", "system_prompt": "Tu aides."}},
    )
    assert brouillon.json()["socle"] is None
    assert ("GET", "/api/v1/groups/") not in faux.appels[-1:]

    archive = await client.delete(f"/api/agents/{res.json()['id']}")
    assert archive.json()["socle"] == "retiree"
    assert res.json()["id"] not in faux.fiches


async def test_fiche_voulue_est_pure():
    agent = _agent(Visibility.ministry, AgentStatus.published)
    config = ConfigSnapshot(name="A", description="")
    fiche = socle.fiche_voulue(agent, config)
    assert fiche["meta"]["description"].startswith("Agent « A »")
    assert socle.fusionner(None, fiche) == fiche
