"""Tests for app.core.security (OIDC/JWT validation)."""

import pytest

from app.core.security import (
    AuthUser,
    OIDCError,
    _extract_user,
    get_current_user,
)


def test_extract_user_admin_role():
    claims = {
        "sub": "00000000-0000-0000-0000-000000000010",
        "preferred_username": "admin",
        "email": "admin@myagents.local",
        "realm_access": {"roles": ["admin", "user", "default-roles-myagents"]},
        "groups": ["/myagents-admin"],
    }
    user = _extract_user(claims)
    assert user.user_id == "00000000-0000-0000-0000-000000000010"
    assert user.username == "admin"
    assert user.email == "admin@myagents.local"
    assert "admin" in user.roles
    assert user.is_admin is True


def test_extract_user_standard_role():
    claims = {
        "sub": "00000000-0000-0000-0000-000000000011",
        "preferred_username": "user1",
        "email": "user1@myagents.local",
        "realm_access": {"roles": ["user", "default-roles-myagents"]},
        "groups": ["/myagents-user"],
    }
    user = _extract_user(claims)
    assert user.user_id == "00000000-0000-0000-0000-000000000011"
    assert user.is_admin is False
    assert "user" in user.roles


def test_extract_user_admin_via_group_only():
    claims = {
        "sub": "abc",
        "preferred_username": "groupadmin",
        "realm_access": {"roles": ["user"]},
        "groups": ["/myagents-admin"],
    }
    user = _extract_user(claims)
    assert user.is_admin is True


def test_extract_user_missing_fields():
    claims = {}
    user = _extract_user(claims)
    assert user.user_id == "unknown"
    assert user.username == ""
    assert user.roles == []
    assert user.is_admin is False


async def test_get_current_user_oidc_disabled_returns_placeholder(monkeypatch):
    """When OIDC is disabled, returns a local-dev placeholder user."""
    from app.core.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "oidc_enabled", False)
    user = await get_current_user(authorization=None)
    assert isinstance(user, AuthUser)
    assert user.user_id == settings.default_user_id


async def test_get_current_user_oidc_enabled_no_token_raises(monkeypatch):
    from app.core.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "oidc_enabled", True)
    monkeypatch.setattr(settings, "oidc_issuer", "http://keycloak:8080/realms/myagents")
    with pytest.raises(OIDCError, match="missing bearer token"):
        await get_current_user(authorization=None)
