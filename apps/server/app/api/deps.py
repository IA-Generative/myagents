"""Request-scoped dependencies (DB session, current user)."""

import hmac

from fastapi import Header, HTTPException

from app.core.config import get_settings
from app.core.security import AuthUser, OIDCError
from app.core.security import get_current_user as _get_current_user


async def get_current_user_id(
    authorization: str | None = Header(default=None),
    x_user_id: str | None = Header(default=None),
) -> str:
    """Return the authenticated user id.

    With OIDC enabled (OIDC_ENABLED=true): validates the Bearer JWT and returns `sub`.
    With OIDC disabled (local dev): returns X-User-ID header or `default_user_id`.
    """
    settings = get_settings()
    if settings.oidc_enabled:
        try:
            user = await _get_current_user(authorization)
        except OIDCError as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc
        return user.user_id
    return x_user_id or settings.default_user_id


async def get_current_user(
    authorization: str | None = Header(default=None),
) -> AuthUser:
    """Full authenticated user (roles, groups, is_admin). Raises 401 if invalid."""
    try:
        return await _get_current_user(authorization)
    except OIDCError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc


async def require_openwebui_key(
    authorization: str | None = Header(default=None),
) -> None:
    """Auth for inbound /v1/* calls: static shared key as a Bearer token."""
    expected = get_settings().openwebui_api_key
    provided = (authorization or "").removeprefix("Bearer ").strip()
    if not expected or not hmac.compare_digest(provided, expected):
        raise HTTPException(status_code=401, detail="invalid_api_key")
