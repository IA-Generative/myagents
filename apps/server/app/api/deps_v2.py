"""Dépendances des routes du contrat de capacités (/api/v2, /mcp) : identité, portées, débit.

Avec le SSO : Bearer seul (jamais de cookie), audience `mesagents`, `azp` et `scope` lus dans le
jeton. Sans SSO (dev et tests, refusé en production par la configuration) : en-têtes `X-User-*`.
La liste des `azp` suspendus est relue à chaque appel (ADR §4.7).
"""

import re
from collections.abc import Awaitable, Callable

from fastapi import Depends, Header, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import ratelimit, security
from app.core.config import get_settings
from app.core.contrat import ContratError
from app.core.portees import Operation, exiger, normaliser_portees
from app.core.security import AudienceError, AuthUser, OIDCError
from app.db.session import get_db
from app.services import suspension

_USER_ID_RE = re.compile(r"^[A-Za-z0-9._:@-]{1,255}$")
_PORTEES_DEV = "mesagents:read mesagents:act mesagents:author"


def en_tete_www_authenticate(erreur: str = "invalid_token") -> dict[str, str]:
    """Découverte RFC 9728 : où est la ressource protégée, pour un client OAuth 2.1 (Open WebUI)."""
    base = get_settings().public_base_url.rstrip("/")
    return {
        "WWW-Authenticate": (
            f'Bearer resource_metadata="{base}/.well-known/oauth-protected-resource/mcp", '
            f'error="{erreur}"'
        )
    }


def _liste(valeur: str | None) -> list[str]:
    if not valeur:
        return []
    return [v for v in re.split(r"[,\s]+", valeur) if v]


def _utilisateur_dev(
    x_user_id: str | None,
    x_user_groups: str | None,
    x_user_azp: str | None,
    x_user_scopes: str | None,
    x_user_roles: str | None,
) -> AuthUser:
    settings = get_settings()
    sub = x_user_id or settings.default_user_id
    if not _USER_ID_RE.match(sub):
        raise ContratError(400, "invalid_request", "identifiant d'utilisateur invalide")
    roles = _liste(x_user_roles)
    return AuthUser(
        user_id=sub,
        username=sub,
        email="",
        roles=roles,
        groups=_liste(x_user_groups),
        is_admin="admin" in roles,
        azp=x_user_azp or "dev-client",
        scopes=tuple(
            sorted(
                normaliser_portees(
                    x_user_scopes if x_user_scopes is not None else _PORTEES_DEV
                )
            )
        ),
    )


async def get_v2_user(
    request: Request,
    authorization: str | None = Header(default=None),
    x_user_id: str | None = Header(default=None),
    x_user_groups: str | None = Header(default=None),
    x_user_azp: str | None = Header(default=None),
    x_user_scopes: str | None = Header(default=None),
    x_user_roles: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> AuthUser:
    settings = get_settings()
    if settings.oidc_enabled:
        try:
            user = await security.get_capability_user(authorization)
        except AudienceError as exc:
            raise ContratError.de("audience_mismatch") from exc
        except OIDCError as exc:
            raise ContratError(
                401, "invalid_token", headers=en_tete_www_authenticate()
            ) from exc
    else:
        user = _utilisateur_dev(
            x_user_id, x_user_groups, x_user_azp, x_user_scopes, x_user_roles
        )
    if await suspension.est_suspendu(db, user.azp):
        raise ContratError(403, "forbidden", "client appelant suspendu")
    request.state.jeton = (
        authorization.split(" ", 1)[1].strip()
        if authorization and authorization.lower().startswith("bearer ")
        else None
    )
    return user


def exiger_portee(operation: Operation) -> Callable[..., Awaitable[AuthUser]]:
    """Fabrique de dépendance : l'identité, puis la portée de l'opération (403 scope_missing)."""

    async def _dep(user: AuthUser = Depends(get_v2_user)) -> AuthUser:
        exiger(user.scopes, operation)
        return user

    return _dep


def limiter(user: AuthUser) -> None:
    """Débit par personne sur ce qui appelle un modèle ou un outil ; 429 + Retry-After."""
    par_minute = get_settings().rate_limit_per_minute
    if par_minute and not ratelimit.allow(f"v2:{user.user_id}", par_minute):
        raise ContratError.de("rate_limited", headers={"Retry-After": "60"})
