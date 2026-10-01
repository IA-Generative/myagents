"""Request-scoped dependencies (DB session, current user)."""

import hmac
import re

from fastapi import Depends, Header, HTTPException

from app.core import ratelimit
from app.core.config import get_settings
from app.core.security import AuthUser, OIDCError
from app.core.security import get_current_user as _get_current_user

_USER_ID_RE = re.compile(r"^[A-Za-z0-9._:@-]{1,255}$")


async def get_current_user_id(
    authorization: str | None = Header(default=None),
    x_user_id: str | None = Header(default=None),
) -> str:
    """Return the authenticated user id.

    With OIDC enabled (OIDC_ENABLED=true): validates the Bearer JWT and returns `sub`.
    With OIDC disabled (local dev only, refused in production): returns X-User-ID header
    or `default_user_id`.
    """
    settings = get_settings()
    if settings.oidc_enabled:
        try:
            user = await _get_current_user(authorization)
        except OIDCError as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc
        return user.user_id
    if x_user_id:
        if not _USER_ID_RE.match(x_user_id):
            raise HTTPException(status_code=400, detail="invalid_user_id")
        return x_user_id
    return settings.default_user_id


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
    """Auth for inbound /v1/* calls: static shared key as a Bearer token.

    The key is always enforced when OPENWEBUI_API_KEY is set. Without a key, calls are
    only allowed in local dev (OIDC_ENABLED=false) so the Swagger UI can test /v1/*.
    """
    settings = get_settings()
    expected = settings.openwebui_api_key
    if not expected:
        if not settings.oidc_enabled:
            return
        raise HTTPException(status_code=401, detail="invalid_api_key")
    provided = (authorization or "").removeprefix("Bearer ").strip()
    if not hmac.compare_digest(provided.encode(), expected.encode()):
        raise HTTPException(status_code=401, detail="invalid_api_key")


async def limit_llm_user(user_id: str = Depends(get_current_user_id)) -> str:
    """Per-user throttle for endpoints that trigger LLM calls."""
    if not ratelimit.allow(user_id, get_settings().rate_limit_per_minute):
        raise HTTPException(status_code=429, detail="rate_limited")
    return user_id


async def limit_llm_openwebui() -> None:
    """Global throttle for the shared Open WebUI connection (no per-user identity)."""
    if not ratelimit.allow("openwebui", get_settings().rate_limit_per_minute * 10):
        raise HTTPException(status_code=429, detail="rate_limited")
