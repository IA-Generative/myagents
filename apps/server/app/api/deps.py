"""Request-scoped dependencies (DB session, current user)."""

import hmac
import re
from urllib.parse import urlsplit

from fastapi import Depends, Header, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import ratelimit
from app.core.config import get_settings
from app.core.security import AuthUser, OIDCError, has_required_group
from app.core.security import get_current_user as _get_current_user
from app.core.session_crypto import SessionCryptoUnavailableError
from app.db.session import get_db
from app.services import auth_sessions

_USER_ID_RE = re.compile(r"^[A-Za-z0-9._:@-]{1,255}$")
_SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


def _origin(url: str) -> str:
    parts = urlsplit(url)
    return f"{parts.scheme}://{parts.netloc}"


def check_csrf(request: Request) -> None:
    """Requêtes mutantes authentifiées par cookie : en-tête custom + Origin attendue."""
    if request.method in _SAFE_METHODS:
        return
    if not request.headers.get("x-requested-with"):
        raise HTTPException(status_code=403, detail="csrf_header_missing")
    settings = get_settings()
    allowed = {_origin(settings.web_public_url), *settings.cors_origins}
    origin = request.headers.get("origin")
    if origin and origin.rstrip("/") not in allowed:
        raise HTTPException(status_code=403, detail="csrf_origin_mismatch")


async def _authenticate(
    request: Request, authorization: str | None, db: AsyncSession
) -> AuthUser:
    """OIDC activé : Bearer JWT Keycloak (clients non navigateur), sinon cookie de session."""
    if authorization:
        try:
            user = await _get_current_user(authorization)
        except OIDCError as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc
    else:
        raw = request.cookies.get(auth_sessions.SESSION_COOKIE)
        if not raw:
            raise HTTPException(status_code=401, detail="missing credentials")
        check_csrf(request)
        try:
            user = await auth_sessions.resolve_session(db, raw)
        except SessionCryptoUnavailableError as exc:
            raise HTTPException(status_code=503, detail="session_unavailable") from exc
        if user is None:
            raise HTTPException(status_code=401, detail="invalid session")
    # Contrôlé à chaque requête : les groupes sont relus à chaque rafraîchissement de session,
    # un retrait du groupe coupe donc l'accès sans attendre la fin de la session.
    if not has_required_group(user):
        raise HTTPException(status_code=403, detail="groupe_requis")
    return user


async def get_current_user_id(
    request: Request,
    authorization: str | None = Header(default=None),
    x_user_id: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> str:
    """Return the authenticated user id.

    With OIDC enabled (OIDC_ENABLED=true): Bearer JWT, or the server-side session cookie set by
    /api/auth/callback (the Vue SPA never handles tokens). With OIDC disabled (local dev only,
    refused in production): returns X-User-ID header or `default_user_id`.
    """
    settings = get_settings()
    if settings.oidc_enabled:
        return (await _authenticate(request, authorization, db)).user_id
    if x_user_id:
        if not _USER_ID_RE.match(x_user_id):
            raise HTTPException(status_code=400, detail="invalid_user_id")
        return x_user_id
    return settings.default_user_id


async def get_current_user(
    request: Request,
    authorization: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> AuthUser:
    """Full authenticated user (roles, groups, is_admin). Raises 401 if invalid."""
    if not get_settings().oidc_enabled:
        return await _get_current_user(None)
    return await _authenticate(request, authorization, db)


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
