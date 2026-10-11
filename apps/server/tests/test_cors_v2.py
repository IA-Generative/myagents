"""CORS et Cache-Control des routes du contrat (ADR §10.0 En-têtes ; C-A12 en local)."""

import pytest

from app.core.config import get_settings
from tests.outils_capacites import entetes

ORIGINE = "https://mysearch-pr-7.beta-preview.example"


@pytest.fixture(autouse=True)
def _origines(monkeypatch):
    monkeypatch.setattr(
        get_settings(),
        "contrat_origines",
        ["https://mysearch-pr-*.beta-preview.example"],
    )


@pytest.mark.parametrize("chemin", ["/api/v2/capabilities", "/mcp"])
async def test_preflight_origine_inconnue_sans_allow_origin(client, chemin):
    res = await client.options(
        chemin,
        headers={
            "Origin": "https://evil.example",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert "access-control-allow-origin" not in {k.lower() for k in res.headers}


@pytest.mark.parametrize("chemin", ["/api/v2/capabilities", "/mcp"])
async def test_preflight_origine_autorisee(client, chemin):
    res = await client.options(
        chemin,
        headers={
            "Origin": ORIGINE,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "authorization, content-type",
        },
    )
    assert res.status_code == 204
    assert res.headers["access-control-allow-origin"] == ORIGINE
    assert "Authorization" in res.headers["access-control-allow-headers"]
    assert "Content-Type" in res.headers["access-control-allow-headers"]
    assert "PATCH" in res.headers["access-control-allow-methods"]
    assert "access-control-allow-credentials" not in {k.lower() for k in res.headers}
    assert "Origin" in res.headers["vary"]
    assert res.headers["cache-control"] == "no-store"


async def test_reponse_porte_no_store_et_vary(client):
    res = await client.get(
        "/api/v2/capabilities", headers={**entetes(), "Origin": ORIGINE}
    )
    assert res.status_code == 200
    assert res.headers["cache-control"] == "no-store"
    assert "Origin" in res.headers["vary"]
    assert res.headers["access-control-allow-origin"] == ORIGINE


async def test_reponse_sans_origine_autorisee_pas_d_allow_origin(client):
    res = await client.get(
        "/api/v2/capabilities", headers={**entetes(), "Origin": "https://evil.example"}
    )
    assert res.status_code == 200
    assert "access-control-allow-origin" not in {k.lower() for k in res.headers}
    assert res.headers["cache-control"] == "no-store"


async def test_catch_all_spa_ne_couvre_pas_mcp_ni_well_known(client):
    """Sans fichiers statiques en test, les chemins hors API répondent 404 ; jamais index.html."""
    res = await client.get("/mcp/inexistant", headers=entetes())
    assert res.status_code in (404, 405)
    res = await client.get("/.well-known/inexistant")
    assert res.status_code == 404
