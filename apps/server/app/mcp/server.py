"""Méthodes du serveur MCP (ADR §4.4) : `initialize`, `ping`, `notifications/initialized`,
`tools/list`, `tools/call`, `prompts/list`, `prompts/get`. Rien d'autre (pas d'écriture par MCP).

Serveur sans état : `Mcp-Session-Id` est émis à l'initialisation et accepté ensuite sans contrôle.
Les versions de protocole parlées sont celles du client Python officiel qu'embarque Open WebUI.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from app.core.config import get_settings
from app.mcp import filtrage, meta_outils
from app.mcp.jsonrpc import INVALID_PARAMS, METHOD_NOT_FOUND, JsonRpcError
from app.services import capabilities as service
from app.services import pins
from app.services.execution import ContexteAppel

VERSIONS_PROTOCOLE: tuple[str, ...] = (
    "2024-11-05",
    "2025-03-26",
    "2025-06-18",
    "2025-11-25",
)
VERSION_DEFAUT = "2025-06-18"
NOM_SERVEUR = "mes-agents"

Handler = Callable[[Any, Any, ContexteAppel, dict], Awaitable[dict]]


def negocier_version(demandee: Any) -> str:
    return (
        demandee
        if isinstance(demandee, str) and demandee in VERSIONS_PROTOCOLE
        else VERSION_DEFAUT
    )


async def initialize(db, user, ctx: ContexteAppel, params: dict) -> dict:
    """Négociation de version et annonce des capacités du serveur (tools, prompts, list_changed)."""
    from app.version import DEV, VERSION_JSON

    try:
        import json

        version_app = json.loads(VERSION_JSON.read_text(encoding="utf-8")).get(
            "version", "dev"
        )
    except OSError, ValueError:
        version_app = DEV["version"]
    return {
        "protocolVersion": negocier_version(params.get("protocolVersion")),
        "capabilities": {
            "tools": {"listChanged": True},
            "prompts": {"listChanged": True},
        },
        "serverInfo": {
            "name": NOM_SERVEUR,
            "title": "Mes agents — capacités gouvernées",
            "version": str(version_app),
        },
        "instructions": (
            "Catalogue de capacités gouvernées du ministère. Cherche d'abord avec rechercher_capacites, "
            "puis exécute avec executer_capacite ; les capacités épinglées par la personne sont servies "
            "directement comme outils."
        ),
    }


async def ping(db, user, ctx: ContexteAppel, params: dict) -> dict:
    """Vie du serveur."""
    return {}


async def tools_list(db, user, ctx: ContexteAppel, params: dict) -> dict:
    """Trois méta-outils + les capacités épinglées (≤ plafond), filtrées par visibilité et par `azp`."""
    settings = get_settings()
    epingles: list[dict] = []
    for cap in await pins.lister(db, user.user_id):
        version = await service.version_servie(db, cap)
        if version is None or cap.status in ("retired", "suspended"):
            continue
        if not await service.visible(db, cap, user):
            continue
        epingles.append(service.forme_outil(cap, version))
    champs = filtrage.champs_fournis(user.azp or "", settings.mesagents_contextes_azp)
    outils = filtrage.construire_tools_list(
        epingles,
        catalogue_taille=0,
        champs=champs,
        plafond=settings.mesagents_epingles_max,
    )
    return {"tools": outils}


async def tools_call(db, user, ctx: ContexteAppel, params: dict) -> dict:
    """Exécution sous l'identité ; méta-outils et capacités épinglées passent par le même chemin."""
    nom = params.get("name")
    if not isinstance(nom, str) or not nom:
        raise JsonRpcError(INVALID_PARAMS, "params.name is required")
    arguments = params.get("arguments")
    if arguments is None:
        arguments = {}
    if not isinstance(arguments, dict):
        raise JsonRpcError(INVALID_PARAMS, "params.arguments must be an object")
    if nom in meta_outils.HANDLERS:
        resultat = await meta_outils.HANDLERS[nom](db, ctx, arguments)
    else:
        from app.services.execution import executer

        resultat = await executer(db, ctx, nom, None, arguments)
    return resultat.mcp()


def _arguments_prompt(input_schema: dict) -> list[dict]:
    proprietes = input_schema.get("properties") or {}
    requis = set(input_schema.get("required") or [])
    return [
        {
            "name": nom,
            "description": str((spec or {}).get("description", "")),
            "required": nom in requis,
        }
        for nom, spec in proprietes.items()
    ]


async def prompts_list(db, user, ctx: ContexteAppel, params: dict) -> dict:
    """Une amorce par capacité `prompt` visible et servie (ses exemples) ; sans pagination."""
    prompts = []
    for cap in await service.lister_visibles(db, user):
        if (
            cap.kind != "prompt"
            or cap.status in ("retired", "suspended")
            or cap.current_version is None
        ):
            continue
        version = service.version_numero(cap, cap.current_version)
        if version is None:
            continue
        prompts.append(
            {
                "name": cap.name,
                "title": version.title,
                "description": version.description[:200],
                "arguments": _arguments_prompt(version.input_schema or {}),
            }
        )
    return {"prompts": prompts}


async def prompts_get(db, user, ctx: ContexteAppel, params: dict) -> dict:
    """L'amorce rendue : les arguments donnés, sinon le premier exemple de la version servie."""
    nom = params.get("name")
    cap = await service.par_nom(db, nom) if isinstance(nom, str) else None
    if cap is None or cap.kind != "prompt" or not await service.visible(db, cap, user):
        raise JsonRpcError(INVALID_PARAMS, "unknown prompt")
    version = await service.version_servie(db, cap)
    if version is None or cap.status in ("retired", "suspended"):
        raise JsonRpcError(INVALID_PARAMS, "unknown prompt")
    arguments = params.get("arguments") or {}
    if arguments and isinstance(arguments, dict):
        from app.services.execution import texte_des_arguments

        texte = texte_des_arguments(version.input_schema or {}, arguments)
    else:
        exemples = version.examples or []
        premier = (
            exemples[0].get("input")
            if exemples and isinstance(exemples[0], dict)
            else None
        )
        if isinstance(premier, dict) and premier:
            from app.services.execution import texte_des_arguments

            texte = texte_des_arguments(version.input_schema or {}, premier)
        else:
            texte = version.title
    return {
        "description": version.description[:200],
        "messages": [{"role": "user", "content": {"type": "text", "text": texte}}],
    }


METHODES: dict[str, Handler] = {
    "initialize": initialize,
    "ping": ping,
    "tools/list": tools_list,
    "tools/call": tools_call,
    "prompts/list": prompts_list,
    "prompts/get": prompts_get,
}

# Notifications du client admises (202, sans réponse).
NOTIFICATIONS_ADMISES: tuple[str, ...] = (
    "notifications/initialized",
    "notifications/cancelled",
    "notifications/roots/list_changed",
)


async def traiter(db, user, ctx: ContexteAppel, method: str, params: dict) -> dict:
    handler = METHODES.get(method)
    if handler is None:
        raise JsonRpcError(METHOD_NOT_FOUND, "Method not found")
    return await handler(db, user, ctx, params)
