"""Client Keycloak Admin REST API : recherche de groupes pour la publication d'agents.

Utilise un compte de service (client_credentials) distinct du flux OIDC utilisateur.
Le token est mis en cache jusqu'à expiration. Les résultats de recherche sont également
mis en cache (TTL 5 min) : les groupes Keycloak changent rarement, et le combobox peut
marteler la route à chaque frappe.
"""

import asyncio
import logging
import time
from dataclasses import dataclass

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)

_SEARCH_CACHE_TTL = 300


@dataclass(frozen=True)
class KcGroup:
    id: str
    name: str
    path: str


class KeycloakAdminError(Exception):
    """Erreur d'appel à l'Admin REST API Keycloak."""


_admin_token: str | None = None
_admin_token_expires: float = 0.0
_search_cache: dict[str, tuple[float, list[KcGroup]]] = {}
_cache_lock = asyncio.Lock()


def _backchannel_realm() -> str:
    settings = get_settings()
    return (settings.oidc_internal_url or settings.oidc_issuer).rstrip("/")


def _split_realm_url() -> tuple[str, str]:
    """(server_root, realm_name) extraits de l'URL du realm.

    http://localhost:8180/realms/myagents → ("http://localhost:8180", "myagents")
    """
    realm_url = _backchannel_realm()
    parts = realm_url.rsplit("/realms/", 1)
    if len(parts) == 2:
        return parts[0], parts[1]
    # Fallback peu probable : l'issuer OIDC est toujours .../realms/{realm}.
    return realm_url, "myagents"


def _trust_env() -> bool:
    return not bool(get_settings().oidc_internal_url)


async def _get_service_account_token() -> str:
    """Obtient (et cache) un token client_credentials pour le compte de service."""
    global _admin_token, _admin_token_expires
    if _admin_token and time.monotonic() < _admin_token_expires - 30:
        return _admin_token
    async with _cache_lock:
        if _admin_token and time.monotonic() < _admin_token_expires - 30:
            return _admin_token
        settings = get_settings()
        async with httpx.AsyncClient(timeout=10, trust_env=_trust_env()) as client:
            try:
                response = await client.post(
                    f"{_backchannel_realm()}/protocol/openid-connect/token",
                    data={
                        "grant_type": "client_credentials",
                        "client_id": settings.oidc_admin_client_id,
                        "client_secret": settings.oidc_admin_client_secret,
                    },
                )
            except httpx.HTTPError as exc:
                raise KeycloakAdminError("admin token request failed") from exc
        if response.status_code != 200:
            raise KeycloakAdminError(
                f"admin token rejected ({response.status_code})"
            )
        body = response.json()
        _admin_token = body["access_token"]
        _admin_token_expires = time.monotonic() + int(body.get("expires_in", 60))
        return _admin_token


async def search_groups(query: str, max_results: int = 20) -> list[KcGroup]:
    """Recherche serveur de groupes Keycloak via l'Admin REST API.

    GET /admin/realms/{realm}/groups?search={query}&max={max_results}
    Le paramètre ``search`` fait une correspondance sous-chaîne (insensible à la casse)
    sur le nom des groupes, sous-groupes inclus, et retourne une liste plate.
    """
    cache_key = f"{query.strip().lower()}:{max_results}"
    now = time.monotonic()
    async with _cache_lock:
        cached = _search_cache.get(cache_key)
        if cached and now < cached[0]:
            return cached[1]

    token = await _get_service_account_token()
    server_root, realm = _split_realm_url()
    async with httpx.AsyncClient(timeout=10, trust_env=_trust_env()) as client:
        try:
            response = await client.get(
                f"{server_root}/admin/realms/{realm}/groups",
                params={
                    "search": query.strip(),
                    "max": max_results,
                    "first": 0,
                    "briefRepresentation": "true",
                },
                headers={"Authorization": f"Bearer {token}"},
            )
        except httpx.HTTPError as exc:
            raise KeycloakAdminError("group search failed") from exc
    if response.status_code != 200:
        raise KeycloakAdminError(
            f"group search rejected ({response.status_code})"
        )
    groups = [
        KcGroup(
            id=g["id"],
            name=g.get("name", ""),
            path=g.get("path", ""),
        )
        for g in response.json()
    ]
    async with _cache_lock:
        _search_cache[cache_key] = (now + _SEARCH_CACHE_TTL, groups)
    return groups


def invalidate_cache() -> None:
    """Vide les caches (pour les tests)."""
    global _admin_token, _admin_token_expires
    _admin_token = None
    _admin_token_expires = 0.0
    _search_cache.clear()
