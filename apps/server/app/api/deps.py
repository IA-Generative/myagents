"""Request-scoped dependencies (DB session, current user)."""

from fastapi import Header

from app.core.config import get_settings


async def get_current_user_id(x_user_id: str | None = Header(default=None)) -> str:
    """Placeholder identity — replace with Keycloak/OIDC token validation later."""
    return x_user_id or get_settings().default_user_id
