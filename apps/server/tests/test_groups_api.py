"""Tests for the groups search API: admin API path and token fallback."""

from unittest.mock import AsyncMock, patch

import pytest

from app.api.deps import get_current_user
from app.core.config import get_settings
from app.core.keycloak_admin import KcGroup, KeycloakAdminError, invalidate_cache
from app.core.security import AuthUser
from app.main import app

TEST_USER = AuthUser(
    user_id="test-user",
    username="tester",
    email="test@example.com",
    roles=["user"],
    groups=["group-a", "group-b", "group-c"],
    is_admin=False,
)


@pytest.fixture(autouse=True)
def _clear_caches():
    invalidate_cache()
    yield
    invalidate_cache()


@pytest.fixture(autouse=True)
def _no_admin_secret(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "oidc_admin_client_secret", "")


@pytest.fixture
def authed_client(client):
    async def override():
        return TEST_USER

    app.dependency_overrides[get_current_user] = override
    yield client
    app.dependency_overrides.pop(get_current_user, None)


async def test_fallback_returns_all_token_groups(authed_client):
    res = await authed_client.get("/api/groups")
    assert res.status_code == 200
    names = [g["name"] for g in res.json()]
    assert names == ["group-a", "group-b", "group-c"]


async def test_fallback_filters_by_query(authed_client):
    res = await authed_client.get("/api/groups?q=group-a")
    assert res.status_code == 200
    names = [g["name"] for g in res.json()]
    assert names == ["group-a"]


async def test_fallback_case_insensitive(authed_client):
    res = await authed_client.get("/api/groups?q=GROUP-A")
    assert res.status_code == 200
    names = [g["name"] for g in res.json()]
    assert names == ["group-a"]


async def test_fallback_no_match(authed_client):
    res = await authed_client.get("/api/groups?q=zzz")
    assert res.status_code == 200
    assert res.json() == []


@patch("app.api.routes.groups.search_groups", new_callable=AsyncMock)
async def test_admin_api_search(mock_search, authed_client, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "oidc_admin_client_secret", "secret")
    mock_search.return_value = [
        KcGroup(id="1", name="group-a", path="/group-a"),
        KcGroup(id="2", name="group-b", path="/group-b"),
    ]
    res = await authed_client.get("/api/groups?q=group-a")
    assert res.status_code == 200
    body = res.json()
    assert len(body) == 2
    assert body[0]["name"] == "group-a"
    assert body[0]["path"] == "/group-a"
    mock_search.assert_called_once_with("group-a")


@patch("app.api.routes.groups.search_groups", new_callable=AsyncMock)
async def test_admin_api_error_falls_back_to_token(mock_search, authed_client, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "oidc_admin_client_secret", "secret")
    mock_search.side_effect = KeycloakAdminError("connection failed")
    res = await authed_client.get("/api/groups?q=group-a")
    assert res.status_code == 200
    names = [g["name"] for g in res.json()]
    assert names == ["group-a"]
