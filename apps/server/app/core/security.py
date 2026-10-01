"""OIDC/JWT validation against Keycloak.

Validates Bearer access tokens issued by Keycloak (realm `myagents`).
Caches JWKS keys to avoid hitting the issuer on every request.

Usage in deps.py::

    from app.core.security import get_current_user

    user: AuthUser = Depends(get_current_user)
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any

import httpx
import jwt
from jwt import PyJWKClient

from app.core.config import get_settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AuthUser:
    """Authenticated user extracted from a validated JWT."""

    user_id: str
    username: str
    email: str
    roles: list[str]
    groups: list[str]
    is_admin: bool


class OIDCError(Exception):
    """Base error for OIDC validation failures."""


class OIDCDisabled(OIDCError):
    """Raised when OIDC is disabled but a caller tried to use the security dep."""


_jwks_client: PyJWKClient | None = None


def _get_jwks_client() -> PyJWKClient:
    global _jwks_client
    if _jwks_client is None:
        settings = get_settings()
        if not settings.oidc_issuer:
            raise OIDCError("OIDC_ISSUER not configured")
        jwks_uri = (
            settings.oidc_jwks_url
            or f"{settings.oidc_issuer.rstrip('/')}/protocol/openid-connect/certs"
        )
        _jwks_client = PyJWKClient(
            jwks_uri,
            cache_keys=True,
            lifespan=settings.oidc_jwks_cache_seconds,
        )
        logger.info("JWKS client initialized: %s", jwks_uri)
    return _jwks_client


def _decode_token(token: str) -> dict[str, Any]:
    """Decode and validate a JWT access token against the Keycloak JWKS."""
    settings = get_settings()
    if not settings.oidc_issuer:
        raise OIDCError("OIDC_ISSUER not configured")

    jwks = _get_jwks_client()
    signing_key = jwks.get_signing_key_from_jwt(token)
    return jwt.decode(
        token,
        signing_key.key,
        algorithms=["RS256"],
        audience=settings.oidc_audience or None,
        issuer=settings.oidc_issuer,
        options={"require": ["exp", "iat", "iss"]},
    )


def _extract_user(claims: dict[str, Any]) -> AuthUser:
    """Map Keycloak claims to AuthUser."""
    roles: list[str] = []
    # Keycloak realm roles come via `realm_access.roles`.
    realm_access = claims.get("realm_access") or {}
    roles = list(realm_access.get("roles", []))
    # Some clients emit a flat `roles` claim too.
    if isinstance(claims.get("roles"), list):
        for r in claims["roles"]:
            if r not in roles:
                roles.append(r)

    groups: list[str] = []
    if isinstance(claims.get("groups"), list):
        groups = list(claims["groups"])

    is_admin = "admin" in roles or "/myagents-admin" in groups

    # Keycloak `sub` is the user UUID.
    user_id = claims.get("sub") or claims.get("preferred_username") or "unknown"
    return AuthUser(
        user_id=str(user_id),
        username=str(claims.get("preferred_username") or ""),
        email=str(claims.get("email") or ""),
        roles=roles,
        groups=groups,
        is_admin=is_admin,
    )


async def get_current_user(authorization: str | None = None) -> AuthUser:
    """Validate the Bearer token and return the AuthUser.

    Raises OIDCError (→ 401) on missing/invalid token.
    """
    settings = get_settings()
    if not settings.oidc_enabled:
        # Fallback local : identité placeholder pour dev sans SSO.
        return AuthUser(
            user_id=settings.default_user_id,
            username="local-dev",
            email="",
            roles=["user"],
            groups=[],
            is_admin=False,
        )

    if not authorization or not authorization.lower().startswith("bearer "):
        raise OIDCError("missing bearer token")

    token = authorization.split(" ", 1)[1].strip()
    try:
        # PyJWKClient fait des appels réseau synchrones : hors de la boucle d'événements.
        claims = await asyncio.to_thread(_decode_token, token)
    except jwt.PyJWTError as exc:
        logger.warning("JWT validation failed: %s", exc)
        raise OIDCError("invalid token") from exc
    except httpx.HTTPError as exc:
        logger.error("JWKS fetch failed: %s", exc)
        raise OIDCError("issuer unavailable") from exc

    return _extract_user(claims)
