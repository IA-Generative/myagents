"""Veilles (chantier 3) : table `schedules`, API `/api/v2/schedules`, exécution par un compte
technique de collecte, résultat déposé dans l'espace de la personne, suppression avec purge,
conservation bornée, export ; jamais deux exécutions par veille et par créneau."""

import json
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from langchain_core.messages import AIMessage

from app.core.config import get_settings
from app.veilles import collecte
from tests.outils_capacites import ALICE, BOB, entetes

pytestmark = pytest.mark.usefixtures(
    "juge_definition_favorable", "garde_noms_favorable", "capacites_de_veille"
)

A = entetes()
B = entetes(sub=BOB)

PAGE = """<html><head><title>Réforme : {n}</title><meta property="article:published_time" content="2026-10-1{n}T08:00:00Z"></head>
<body><article><p>Le texte {n} modifie les conditions. Détail détail détail.</p></article></body></html>"""
LISTE = """<html><head><title>Actualités</title></head><body>
<a href="/actu/1">Réforme du séjour, épisode 1</a><a href="/actu/2">Réforme du séjour, épisode 2</a><a href="/autre">Sans rapport</a></body></html>"""


@pytest.fixture
def site(monkeypatch):
    """Un site institutionnel simulé : une page d'actualités et deux articles."""
    monkeypatch.setattr(
        get_settings(), "veille_domaines_autorises", ["www.interieur.gouv.fr"]
    )
    monkeypatch.setattr(get_settings(), "veille_contact", "contact@example.gouv.fr")
    monkeypatch.setattr(
        get_settings(), "veille_seeds", ["https://www.interieur.gouv.fr/actualites"]
    )

    def handler(request: httpx.Request) -> httpx.Response:
        chemin = request.url.path
        if chemin == "/robots.txt":
            return httpx.Response(404)
        if chemin == "/actualites":
            return httpx.Response(
                200, text=LISTE, headers={"Content-Type": "text/html"}
            )
        if chemin.startswith("/actu/"):
            return httpx.Response(
                200,
                text=PAGE.replace("{n}", chemin[-1]),
                headers={"Content-Type": "text/html"},
            )
        return httpx.Response(404)

    monkeypatch.setattr(collecte, "_transport_pour_tests", httpx.MockTransport(handler))


def _appel(nom, args, id="c1"):
    return AIMessage(
        content="",
        tool_calls=[{"name": nom, "args": args, "id": id, "type": "tool_call"}],
    )


async def _creer(client, h=A, **kw):
    corps = {
        "sujet": "réforme du séjour",
        "sources": ["web"],
        "cron": "0 7 * * *",
        **kw,
    }
    res = await client.post("/api/v2/schedules", json=corps, headers=h)
    assert res.status_code == 201, res.text
    return res.json()


# --- Création, finalité, minimisation ---------------------------------------------------


async def test_creation_affiche_la_finalite_et_les_champs_necessaires_seulement(client):
    veille = await _creer(client)
    assert (
        veille["sujet"] == "réforme du séjour"
        and veille["cron"] == "0 7 * * *"
        and veille["actif"] is True
    )
    assert veille["sources"] == ["web"] and veille["conservation_jours"] == 90
    assert set(veille) <= {
        "id",
        "sujet",
        "sources",
        "cron",
        "actif",
        "conservation_jours",
        "created_at",
        "updated_at",
        "derniere_execution",
        "finalite",
    }
    assert "finalite" in veille and "veille" in veille["finalite"].lower()
    liste = await client.get("/api/v2/schedules", headers=A)
    assert liste.json()["finalite"] == veille["finalite"]
    assert [v["id"] for v in liste.json()["schedules"]] == [veille["id"]]
    assert (await client.get("/api/v2/schedules", headers=B)).json()["schedules"] == []


async def test_preset_de_frequence_accepte(client):
    veille = await _creer(client, cron="quotidienne")
    assert veille["cron"] == "0 7 * * *"


@pytest.mark.parametrize(
    "corps",
    [{"cron": "0 7 * *"}, {"sources": ["tiktok"]}, {"sujet": ""}, {"sujet": "x" * 300}],
)
async def test_creation_invalide(client, corps):
    res = await client.post(
        "/api/v2/schedules",
        json={"sujet": "réforme", "sources": ["web"], "cron": "0 7 * * *", **corps},
        headers=A,
    )
    assert res.status_code == 400 and res.json()["error"]["code"] == "invalid_request"


async def test_sujet_nominatif_bloque(client, monkeypatch):
    from app.veilles import garde_noms

    async def _refus(sujet, **_):
        return garde_noms.VerdictSujet(
            False, "sujet reconnu comme une personne physique"
        )

    monkeypatch.setattr(garde_noms, "verifier_sujet", _refus)
    res = await client.post(
        "/api/v2/schedules",
        json={"sujet": "Jean Dupont", "sources": ["web"], "cron": "0 7 * * *"},
        headers=A,
    )
    assert res.status_code == 422 and res.json()["error"]["code"] == "guard_rejected"
    assert any("personne" in d for d in res.json()["error"]["details"])


async def test_sans_portee_author_403(client):
    res = await client.post(
        "/api/v2/schedules",
        json={"sujet": "réforme", "sources": ["web"], "cron": "0 7 * * *"},
        headers=entetes(portees="mesagents:read"),
    )
    assert res.status_code == 403 and res.json()["error"]["code"] == "scope_missing"


# --- Exécution forcée, résultat, traçabilité ----------------------------------------------


async def test_execution_forcee_depose_un_resultat_genere_avec_sources(
    client, fake_llm, site
):
    veille = await _creer(client)
    fake_llm.responses[:] = [
        _appel("web.collecter", {"query": "réforme du séjour"}),
        AIMessage(
            "Synthèse : le texte 1 et le texte 2 modifient les conditions (sources : https://www.interieur.gouv.fr/actu/1, https://www.interieur.gouv.fr/actu/2)."
        ),
    ]
    res = await client.post(f"/api/v2/schedules/{veille['id']}/run", headers=A)
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "ok" and res.json()["result_id"]
    res = await client.get(f"/api/v2/schedules/{veille['id']}/results", headers=A)
    resultats = res.json()["results"]
    assert len(resultats) == 1
    r = resultats[0]
    assert r["generated"] is True
    assert r["synthese"].startswith("Synthèse")
    assert [s["url"] for s in r["sources"]] == [
        "https://www.interieur.gouv.fr/actu/1",
        "https://www.interieur.gouv.fr/actu/2",
    ]
    assert all(
        len(s["extrait"]) <= 300 and s["title"] and s["date"] for s in r["sources"]
    )
    assert "Détail détail détail." not in json.dumps(
        r
    )  # jamais le texte intégral… ici l'extrait court le contient ? non : extrait ≤ 300
    assert set(r["urls_consultees"]) >= {
        "https://www.interieur.gouv.fr/actualites",
        "https://www.interieur.gouv.fr/actu/1",
        "https://www.interieur.gouv.fr/actu/2",
    }
    assert r["expires_at"] > r["created_at"]
    # Journalisée comme toute capacité : compte technique de collecte, jamais l'identité de la personne.
    cap = await client.get("/api/v2/capabilities", headers=A)
    veille_cap = next(t for t in cap.json()["tools"] if t["name"] == "veille.synthese")
    runs = await client.get(
        f"/api/v2/capabilities/{veille_cap['id']}/runs",
        headers=entetes(
            sub="revue",
            roles="mesagents-reviewer",
            portees="mesagents:read mesagents:review",
        ),
    )
    lignes = [json.loads(l) for l in runs.text.splitlines() if l.strip()]
    assert (
        lignes
        and lignes[-1]["sub"] == "service:veilles"
        and lignes[-1]["azp"] == "mes-agents-cron"
    )
    assert lignes[-1]["route"].startswith("cron")
    assert "réforme du séjour" not in runs.text
    # Le résultat est dans l'espace de la personne, pas ailleurs.
    assert (
        await client.get(f"/api/v2/schedules/{veille['id']}/results", headers=B)
    ).status_code == 404


async def test_jamais_deux_executions_par_creneau(client, fake_llm, site):
    veille = await _creer(client)
    fake_llm.responses[:] = [AIMessage("Synthèse 1."), AIMessage("Synthèse 2.")]
    r1 = await client.post(f"/api/v2/schedules/{veille['id']}/run", headers=A)
    r2 = await client.post(f"/api/v2/schedules/{veille['id']}/run", headers=A)
    assert r1.json()["status"] == "ok"
    assert (
        r2.json()["status"] == "deja_executee"
        and r2.json()["result_id"] == r1.json()["result_id"]
    )
    assert (
        len(
            (
                await client.get(f"/api/v2/schedules/{veille['id']}/results", headers=A)
            ).json()["results"]
        )
        == 1
    )


async def test_tick_execute_les_creneaux_dus_une_fois(
    client, db_session, fake_llm, site
):
    from app.veilles.tick import tick

    veille = await _creer(client, cron="*/30 * * * *")
    fake_llm.responses[:] = [
        AIMessage("Synthèse a."),
        AIMessage("Synthèse b."),
        AIMessage("Synthèse c."),
    ]
    maintenant = datetime(2026, 10, 12, 8, 31, tzinfo=UTC)
    bilan = await tick(
        db_session, maintenant=maintenant, depuis=maintenant - timedelta(hours=1)
    )
    assert bilan["executees"] == 2  # 08:00 et 08:30
    # Le battement suivant repart du dernier créneau joué : rien à rejouer, rien à ignorer.
    bilan = await tick(
        db_session, maintenant=maintenant, depuis=maintenant - timedelta(hours=1)
    )
    assert bilan["executees"] == 0 and bilan["ignorees"] == 0
    # Un créneau déjà joué, resoumis de force, est ignoré (une exécution par créneau).
    from app.services import veilles as service_veilles

    s = await service_veilles.obtenir(
        db_session, __import__("uuid").UUID(veille["id"]), ALICE
    )
    status, _ = await service_veilles.executer(
        db_session, s, maintenant.replace(minute=30), route="cron"
    )
    assert status == "deja_executee"
    res = await client.get(f"/api/v2/schedules/{veille['id']}/results", headers=A)
    assert len(res.json()["results"]) == 2
    veille_relue = (
        await client.get(f"/api/v2/schedules/{veille['id']}", headers=A)
    ).json()
    assert veille_relue["derniere_execution"]


async def test_veille_inactive_ignoree_par_le_tick(client, db_session, fake_llm, site):
    from app.veilles.tick import tick

    veille = await _creer(client, cron="*/30 * * * *", actif=False)
    bilan = await tick(
        db_session,
        maintenant=datetime(2026, 10, 12, 8, 31, tzinfo=UTC),
        depuis=datetime(2026, 10, 12, 7, 31, tzinfo=UTC),
    )
    assert bilan["executees"] == 0
    assert (
        await client.get(f"/api/v2/schedules/{veille['id']}/results", headers=A)
    ).json()["results"] == []


# --- Suppression, purge, conservation, export -------------------------------------------


async def test_suppression_purge_les_resultats(client, fake_llm, site):
    veille = await _creer(client)
    fake_llm.responses[:] = [AIMessage("Synthèse.")]
    await client.post(f"/api/v2/schedules/{veille['id']}/run", headers=A)
    res = await client.delete(f"/api/v2/schedules/{veille['id']}", headers=A)
    assert res.status_code == 200 and res.json() == {
        "deleted": True,
        "results_purged": 1,
    }
    assert (
        await client.get(f"/api/v2/schedules/{veille['id']}", headers=A)
    ).status_code == 404
    assert (
        await client.get(f"/api/v2/schedules/{veille['id']}/results", headers=A)
    ).status_code == 404
    assert (
        await client.delete(f"/api/v2/schedules/{veille['id']}", headers=B)
    ).status_code == 404


async def test_resultats_expires_purges_par_le_tick(
    client, db_session, fake_llm, site, monkeypatch
):
    from app.veilles.tick import tick

    monkeypatch.setattr(get_settings(), "veille_conservation_jours", 1)
    veille = await _creer(client)
    fake_llm.responses[:] = [AIMessage("Vieille synthèse.")]
    await client.post(f"/api/v2/schedules/{veille['id']}/run", headers=A)
    assert (
        len(
            (
                await client.get(f"/api/v2/schedules/{veille['id']}/results", headers=A)
            ).json()["results"]
        )
        == 1
    )
    plus_tard = datetime.now(UTC) + timedelta(days=2)
    bilan = await tick(
        db_session, maintenant=plus_tard, depuis=plus_tard - timedelta(minutes=1)
    )
    assert bilan["purges"] == 1
    assert (
        await client.get(f"/api/v2/schedules/{veille['id']}/results", headers=A)
    ).json()["results"] == []


async def test_export_de_ses_veilles(client, fake_llm, site):
    veille = await _creer(client)
    fake_llm.responses[:] = [AIMessage("Synthèse exportée.")]
    await client.post(f"/api/v2/schedules/{veille['id']}/run", headers=A)
    res = await client.get("/api/v2/schedules/export", headers=A)
    assert res.status_code == 200
    export = res.json()
    assert export["sub"] == ALICE and len(export["schedules"]) == 1
    assert export["schedules"][0]["results"][0]["synthese"] == "Synthèse exportée."
    assert res.headers["content-disposition"].startswith("attachment")


async def test_modification(client):
    veille = await _creer(client)
    res = await client.patch(
        f"/api/v2/schedules/{veille['id']}",
        json={"cron": "hebdomadaire", "actif": False},
        headers=A,
    )
    assert (
        res.status_code == 200
        and res.json()["cron"] == "0 7 * * 1"
        and res.json()["actif"] is False
    )
    assert (
        await client.patch(
            f"/api/v2/schedules/{veille['id']}", json={"cron": "x"}, headers=A
        )
    ).status_code == 400
    assert (
        await client.patch(
            f"/api/v2/schedules/{veille['id']}", json={"actif": True}, headers=B
        )
    ).status_code == 404
