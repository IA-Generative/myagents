"""Request-scoped dependencies (DB session, current user)."""

import hmac

from fastapi import Header, HTTPException

from app.core.config import get_settings


async def get_current_user_id(x_user_id: str | None = Header(default=None)) -> str:
    """Placeholder identity — replace with Keycloak/OIDC token validation later."""
    return x_user_id or get_settings().default_user_id


async def require_openwebui_key(
    authorization: str | None = Header(default=None),
) -> None:
    """Auth for inbound /v1/* calls: static shared key as a Bearer token."""
    expected = get_settings().openwebui_api_key
    provided = (authorization or "").removeprefix("Bearer ").strip()
    if not expected or not hmac.compare_digest(provided, expected):
        raise HTTPException(status_code=401, detail="invalid_api_key")
