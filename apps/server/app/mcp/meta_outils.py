"""Les trois méta-outils (ADR §4.4 point 1) : chercher, décrire, exécuter. La recherche et la
description sont filtrées par identité et journalisées comme toute exécution."""

from __future__ import annotations

import json
import time
from typing import Any

from app.core.config import get_settings
from app.llm.guard.core import ruleset_version
from app.services import capabilities as service
from app.services import journal
from app.services.execution import ContexteAppel, ResultatOutil, executer, refus

DEFINITIONS: list[dict[str, Any]] = [
    {
        "name": "rechercher_capacites",
        "title": "Rechercher une capacité",
        "description": (
            "Cherche dans le catalogue des capacités accessibles à la personne (texte libre : "
            "ce qu'il faut faire). Renvoie au plus dix capacités (nom, titre, description courte, "
            "maturité). Appelle ensuite executer_capacite avec le nom retenu."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Ce qu'il faut faire, en langage naturel",
                    "maxLength": 200,
                },
                "limit": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 10,
                    "default": 10,
                },
            },
            "required": ["query"],
        },
        "annotations": {
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
        "_meta": {
            "hash": None,
            "version": None,
            "maturity": "general",
            "grounding": "input",
        },
    },
    {
        "name": "decrire_capacite",
        "title": "Décrire une capacité",
        "description": "Le schéma complet (arguments attendus, annotations, version) d'une capacité nommée.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Nom de la capacité"},
                "version": {"type": "integer", "minimum": 1},
            },
            "required": ["name"],
        },
        "annotations": {
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
        "_meta": {
            "hash": None,
            "version": None,
            "maturity": "general",
            "grounding": "input",
        },
    },
    {
        "name": "executer_capacite",
        "title": "Exécuter une capacité",
        "description": (
            "Exécute une capacité du catalogue sous l'identité de la personne : nom, version "
            "(facultative), arguments conformes à son schéma. Les refus sont rendus en erreur lisible."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Nom de la capacité"},
                "version": {"type": "integer", "minimum": 1},
                "arguments": {
                    "type": "object",
                    "description": "Arguments conformes au schéma de la capacité",
                },
            },
            "required": ["name", "arguments"],
        },
        "annotations": {
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": False,
            "openWorldHint": True,
        },
        "_meta": {
            "hash": None,
            "version": None,
            "maturity": "general",
            "grounding": "input",
        },
    },
]

NOMS = tuple(d["name"] for d in DEFINITIONS)


async def _journaliser_meta(
    db, ctx: ContexteAppel, nom: str, debut: float, status: str = "ok"
) -> None:
    await journal.ecrire(
        db,
        capability=nom,
        capability_id=None,
        version=None,
        hash=None,
        sub=ctx.user.user_id,
        azp=ctx.user.azp or "",
        scope_used="mesagents:read",
        guard_in="n/a",
        guard_out="n/a",
        ruleset_version=ruleset_version(),
        duration_ms=int((time.perf_counter() - debut) * 1000),
        status=status,
        route=ctx.route,
    )


def _resume(cap, version) -> dict[str, Any]:
    description = (version.description if version else cap.description) or ""
    return {
        "name": cap.name,
        "title": version.title if version else cap.title,
        "description": description[:200],
        "maturity": version.maturity if version else None,
        "grounding": cap.grounding,
        "readOnlyHint": bool(
            (version.annotations if version else cap.annotations or {}).get(
                "readOnlyHint", False
            )
        ),
        "version": version.version if version else None,
    }


async def rechercher_capacites(
    db, ctx: ContexteAppel, arguments: dict
) -> ResultatOutil:
    debut = time.perf_counter()
    texte = str(arguments.get("query", "") or "")
    if not texte.strip():
        return refus("invalid_request", "argument requis manquant : query")
    limite = min(
        int(arguments.get("limit") or get_settings().mesagents_recherche_max),
        get_settings().mesagents_recherche_max,
    )
    caps = await service.rechercher(db, ctx.user, texte[:200], limite)
    resumes = [_resume(c, service.version_numero(c, c.current_version)) for c in caps]
    await _journaliser_meta(db, ctx, "rechercher_capacites", debut)
    lignes = [
        f"- {r['name']} (v{r['version']}, {r['maturity']}) : {r['title']} — {r['description']}"
        for r in resumes
    ]
    return ResultatOutil(
        texte="\n".join(lignes) if lignes else "Aucune capacité ne correspond.",
        structured={"capabilities": resumes},
        meta={"count": len(resumes)},
    )


async def decrire_capacite(db, ctx: ContexteAppel, arguments: dict) -> ResultatOutil:
    debut = time.perf_counter()
    nom = str(arguments.get("name", "") or "")
    cap = await service.par_nom(db, nom) if nom else None
    if cap is None or not await service.visible(db, cap, ctx.user):
        return refus("not_found")
    numero = arguments.get("version")
    version = (
        service.version_numero(cap, int(numero))
        if numero
        else await service.version_servie(db, cap)
    )
    if version is None:
        return refus("not_found")
    forme = service.forme_outil(cap, version)
    await _journaliser_meta(db, ctx, "decrire_capacite", debut)
    return ResultatOutil(
        texte=json.dumps(forme, ensure_ascii=False, indent=2),
        structured=forme,
        meta=dict(forme["_meta"]),
    )


async def executer_capacite(db, ctx: ContexteAppel, arguments: dict) -> ResultatOutil:
    nom = arguments.get("name")
    if not isinstance(nom, str) or not nom:
        return refus("invalid_request", "argument requis manquant : name")
    version = arguments.get("version")
    if version is not None and not isinstance(version, int):
        return refus("invalid_request", "argument version : type attendu integer")
    args = arguments.get("arguments")
    if args is None:
        args = {}
    return await executer(db, ctx, nom, version, args)


HANDLERS = {
    "rechercher_capacites": rechercher_capacites,
    "decrire_capacite": decrire_capacite,
    "executer_capacite": executer_capacite,
}
