"""Métadonnées de ressource protégée (RFC 9728) : où un client OAuth 2.1 (Open WebUI) trouve le
serveur d'autorisation et les portées de Mes agents. Public, hors authentification."""

from fastapi import APIRouter

from app.core.config import get_settings
from app.core.portees import PORTEES_CONNUES

router = APIRouter(tags=["mcp"])


def _metadonnees() -> dict:
    settings = get_settings()
    return {
        "resource": f"{settings.public_base_url.rstrip('/')}/mcp",
        "authorization_servers": [settings.oidc_issuer] if settings.oidc_issuer else [],
        "scopes_supported": list(PORTEES_CONNUES),
        "bearer_methods_supported": ["header"],
        "resource_name": "Mes agents",
        "resource_documentation": f"{settings.public_base_url.rstrip('/')}/docs/contrats/contrat-capacites-mirai.md",
    }


@router.get(
    "/.well-known/oauth-protected-resource",
    summary="Métadonnées OAuth de la ressource protégée",
)
async def metadonnees():
    return _metadonnees()


@router.get(
    "/.well-known/oauth-protected-resource/mcp",
    summary="Métadonnées OAuth du point d'accès MCP",
)
async def metadonnees_mcp():
    return _metadonnees()
