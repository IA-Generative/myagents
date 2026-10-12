"""Chantier 3 — intégration d'une veille complète en Docker : création, exécution forcée (compte
technique de collecte, Légifrance par le serveur MCP de dépendance et site institutionnel simulé),
résultat généré avec sources, journal, suppression avec purge."""

import json
import os

from tests.conformite.conftest import compose_only

PORTEES = "mesagents:read mesagents:act mesagents:author"
REVUE = "mesagents:read mesagents:act mesagents:author mesagents:review"


@compose_only
def test_veille_legifrance_et_web_complete(api, jeton, suffixe):
    alice = jeton("alice", portees=PORTEES)
    revue = jeton("revue", portees=REVUE)
    res = api.get("/api/v2/schedules", alice)
    assert res.status_code == 200 and "finalite" in res.json()
    res = api.post(
        "/api/v2/schedules",
        alice,
        json={
            "sujet": f"réforme du séjour {suffixe}",
            "sources": ["legifrance", "web"],
            "cron": "quotidienne",
        },
    )
    assert res.status_code == 201, res.text
    veille = res.json()
    try:
        res = api.post(f"/api/v2/schedules/{veille['id']}/run", alice)
        assert res.status_code == 200, res.text
        assert res.json()["status"] == "ok", res.json()
        resultats = api.get(f"/api/v2/schedules/{veille['id']}/results", alice).json()[
            "results"
        ]
        assert len(resultats) == 1
        r = resultats[0]
        assert r["generated"] is True and r["synthese"]
        assert any(s["url"].startswith("http://site-fake") for s in r["sources"]), r[
            "sources"
        ]
        assert all(len(s["extrait"]) <= 300 for s in r["sources"])
        assert any(u.endswith("/actualites") for u in r["urls_consultees"])
        assert not any("/prive/" in u for u in r["urls_consultees"])
        # Journalisée comme toute capacité, par le compte technique, avec ses dépendances.
        caps = api.get("/api/v2/capabilities", revue).json()["tools"]
        veille_cap = next(t for t in caps if t["name"] == "veille.synthese")
        lignes = [
            json.loads(l)
            for l in api.get(
                f"/api/v2/capabilities/{veille_cap['id']}/runs", revue
            ).text.splitlines()
            if l.strip()
        ]
        assert (
            lignes
            and lignes[-1]["sub"] == "service:veilles"
            and lignes[-1]["azp"] == "mes-agents-cron"
        )
        parent = lignes[-1]["run_id"]

        # Les appels de dépendance sont journalisés sous la capacité appelée, rattachés au
        # parent par `parent_run_id`.
        def enfants(nom: str) -> list[dict]:
            cap = next(t for t in caps if t["name"] == nom)
            texte = api.get(f"/api/v2/capabilities/{cap['id']}/runs", revue).text
            return [
                l
                for l in (json.loads(x) for x in texte.splitlines() if x.strip())
                if l["parent_run_id"] == parent and l["route"] == "dependency"
            ]

        assert enfants("web.collecter"), (
            "web.collecter non journalisée comme dépendance"
        )
        if os.environ.get("MCP_FAKE_URL"):
            assert enfants("legifrance.rechercher"), (
                "legifrance.rechercher non journalisée"
            )
    finally:
        res = api.delete(f"/api/v2/schedules/{veille['id']}", alice)
        assert res.status_code == 200 and res.json()["deleted"] is True
    assert (
        api.get(f"/api/v2/schedules/{veille['id']}/results", alice).status_code == 404
    )


@compose_only
def test_sujet_nominatif_refuse(api, jeton):
    alice = jeton("alice", portees=PORTEES)
    res = api.post(
        "/api/v2/schedules",
        alice,
        json={"sujet": "Jean Dupont", "sources": ["web"], "cron": "quotidienne"},
    )
    assert res.status_code == 422 and res.json()["error"]["code"] == "guard_rejected"
