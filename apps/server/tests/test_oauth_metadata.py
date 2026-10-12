"""Métadonnées de ressource protégée (RFC 9728) pour la découverte OAuth 2.1 des clients MCP."""

import pytest

from app.core.config import get_settings


@pytest.fixture(autouse=True)
def _issuer(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "oidc_issuer", "https://sso.example/realms/preview")
    monkeypatch.setattr(s, "public_base_url", "https://mesagents.example")


@pytest.mark.parametrize(
    "chemin",
    [
        "/.well-known/oauth-protected-resource",
        "/.well-known/oauth-protected-resource/mcp",
    ],
)
async def test_metadonnees(client, chemin):
    res = await client.get(chemin)
    assert res.status_code == 200
    corps = res.json()
    assert corps["resource"] == "https://mesagents.example/mcp"
    assert corps["authorization_servers"] == ["https://sso.example/realms/preview"]
    assert set(corps["scopes_supported"]) >= {
        "mesagents:read",
        "mesagents:act",
        "mesagents:author",
        "mesagents:review",
    }
    assert "mesagents:delegate" in corps["scopes_supported"]
    assert corps["bearer_methods_supported"] == ["header"]
    assert res.headers["cache-control"] == "no-store"
