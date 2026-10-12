"""Chemin d'exécution UNIQUE d'une capacité (ADR §10.1 points 4 et 5), partagé par `tools/call`,
`executer_capacite`, `POST /{id}/test` et les dépendances.

Dans l'ordre : résolution (invisible ou non servie → not_found) ; portée selon `readOnlyHint` ;
arguments contre `input_schema` ; garde d'entrée ; exécution selon le genre ; garde de sortie ;
UNE ligne de journal ; résultat d'outil (`isError` sur tout refus, pour que le modèle le lise).
"""

from __future__ import annotations

import json
import logging
import re
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

import openai
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.contrat import ERREURS, ContratError
from app.core.portees import Operation, exiger, portee_pour_appel
from app.core.security import AuthUser
from app.llm.agent_runtime import _is_model_not_found
from app.llm.capability_runtime import arun_capability, specification_outil
from app.llm.client import LlmClient
from app.llm.guard import (
    BLOCK_MESSAGE_OUTPUT,
    BLOCK_MESSAGE_USER_INPUT,
    harden_system_prompt,
    make_canary,
)
from app.llm.guard.core import ruleset_version
from app.models.capability import Capability, CapabilityVersion
from app.services import capabilities as service
from app.services import capability_guard, journal, relais
from app.services.capabilities import lecture_seule
from app.services.relais import RelaisError

logger = logging.getLogger(__name__)

_SLUG = re.compile(r"^[a-z0-9][a-z0-9._-]{2,63}$")


@dataclass
class ContexteAppel:
    user: AuthUser
    jeton: str | None
    route: str
    parent_run_id: uuid.UUID | None = None
    profondeur: int = 0


@dataclass
class ResultatOutil:
    texte: str
    is_error: bool = False
    code: str | None = None
    meta: dict[str, Any] = field(default_factory=dict)
    structured: dict[str, Any] | None = None

    def mcp(self) -> dict[str, Any]:
        corps: dict[str, Any] = {
            "content": [{"type": "text", "text": self.texte}],
            "isError": self.is_error,
            "_meta": dict(self.meta),
        }
        if self.code:
            corps["_meta"]["error"] = {"code": self.code, "message": self.texte}
        if self.structured is not None:
            corps["structuredContent"] = self.structured
        return corps


def refus(code: str, message: str | None = None, **meta) -> ResultatOutil:
    texte = message or ERREURS.get(code, (0, "Refusé."))[1]
    return ResultatOutil(texte=texte, is_error=True, code=code, meta=meta)


# --- Arguments ---------------------------------------------------------------------------------

_TYPES = {
    "string": str,
    "number": (int, float),
    "integer": int,
    "boolean": bool,
    "object": dict,
    "array": list,
}


def valider_arguments(schema: dict, arguments: Any) -> str | None:
    """Validation minimale (requis, type, enum, maxLength au premier niveau) ; message ou None."""
    if not isinstance(arguments, dict):
        return "les arguments doivent former un objet"
    proprietes = schema.get("properties") or {}
    for requis in schema.get("required") or []:
        if requis not in arguments or arguments[requis] is None:
            return f"argument requis manquant : {requis}"
    for nom, valeur in arguments.items():
        spec = proprietes.get(nom)
        if spec is None:
            if schema.get("additionalProperties") is False:
                return f"argument inconnu : {nom}"
            continue
        attendu = _TYPES.get(spec.get("type", ""))
        if attendu is not None and not isinstance(valeur, attendu):
            return f"argument {nom} : type attendu {spec.get('type')}"
        if isinstance(valeur, bool) and spec.get("type") in ("number", "integer"):
            return f"argument {nom} : type attendu {spec.get('type')}"
        if "enum" in spec and valeur not in spec["enum"]:
            return f"argument {nom} : valeur hors de l'énumération"
        if (
            isinstance(valeur, str)
            and "maxLength" in spec
            and len(valeur) > int(spec["maxLength"])
        ):
            return f"argument {nom} : trop long"
    return None


def texte_des_arguments(schema: dict, arguments: dict) -> str:
    """Le matériau soumis au modèle : l'unique champ chaîne requis, sinon un bloc JSON."""
    requis = [
        r for r in (schema.get("required") or []) if isinstance(arguments.get(r), str)
    ]
    if len(requis) == 1 and len(arguments) == 1:
        return arguments[requis[0]]
    return json.dumps(arguments, ensure_ascii=False, indent=2)


def _texte_de_la_garde(arguments: dict) -> str:
    return "\n".join(str(v) for v in arguments.values() if isinstance(v, str))


# --- Exécution ---------------------------------------------------------------------------------


async def executer(
    db: AsyncSession,
    ctx: ContexteAppel,
    name: str,
    version: int | None,
    arguments: Any,
    *,
    brouillon: Capability | None = None,
) -> ResultatOutil:
    """Exécute `name@version` pour la personne du contexte ; `brouillon` = test par l'auteur."""
    debut = time.perf_counter()
    run_id = uuid.uuid4()
    settings = get_settings()

    if brouillon is not None:
        cap, forme = brouillon, brouillon
        numero, empreinte, maturity = None, None, None
    else:
        if not isinstance(name, str) or not _SLUG.match(name):
            return refus("not_found")
        cap = await service.par_nom(db, name)
        if cap is None:
            return refus("not_found")
        servie = await service.version_servie(db, cap)
        if (
            not await service.visible(db, cap, ctx.user)
            or servie is None
            or cap.status in ("retired", "suspended")
        ):
            return refus("not_found")
        forme = service.version_numero(cap, version) if version is not None else servie
        if forme is None:
            return refus(
                "not_found", f"la version {version} de « {name} » n'existe pas"
            )
        numero, empreinte, maturity = forme.version, forme.hash, forme.maturity

    annotations = forme.annotations or {}
    portee = portee_pour_appel(lecture_seule(annotations))
    base_journal = {
        "capability": cap.name,
        "capability_id": cap.id,
        "version": numero,
        "hash": empreinte,
        "sub": ctx.user.user_id,
        "azp": ctx.user.azp or "",
        "scope_used": portee,
        "ruleset_version": ruleset_version(),
        "route": ctx.route,
        "parent_run_id": ctx.parent_run_id,
        "run_id": run_id,
    }

    async def journaliser(
        status: str, guard_in: str = "n/a", guard_out: str = "n/a"
    ) -> None:
        await journal.ecrire(
            db,
            **base_journal,
            guard_in=guard_in,
            guard_out=guard_out,
            duration_ms=int((time.perf_counter() - debut) * 1000),
            status=status,
        )

    meta = {
        "hash": empreinte,
        "version": numero,
        "maturity": maturity,
        "generated": forme.grounding == "open",
    }

    try:
        exiger(
            ctx.user.scopes,
            Operation.APPELER_LECTURE
            if portee == "mesagents:read"
            else Operation.APPELER_ACTION,
        )
    except ContratError as exc:
        await journaliser("scope_missing")
        return refus(
            getattr(exc, "code", "scope_missing"),
            str(getattr(exc, "message", exc)),
            **meta,
        )

    if ctx.route != "dependency":
        from app.api.deps_v2 import limiter

        try:
            limiter(ctx.user)
        except ContratError as exc:
            await journaliser("rate_limited")
            return refus("rate_limited", exc.message, **meta)

    erreur = valider_arguments(forme.input_schema or {}, arguments)
    if erreur:
        await journaliser("invalid_request")
        return refus("invalid_request", erreur, **meta)

    guard_in = await capability_guard.io_entree(
        db, _texte_de_la_garde(arguments), route=ctx.route, user_id=ctx.user.user_id
    )
    if guard_in == "blocked":
        await journaliser("guard_blocked", guard_in=guard_in)
        return refus("blocked_input", BLOCK_MESSAGE_USER_INPUT, **meta)

    canary = make_canary()
    try:
        if cap.kind == "prompt":
            texte = await _executer_prompt(
                db, ctx, cap, forme, arguments, canary, run_id
            )
        else:
            texte = await _executer_relais(ctx, cap, forme, arguments)
    except RelaisError as exc:
        logger.warning("[capacite] relais %s en échec : %s", cap.name, exc)
        await journaliser("upstream_error", guard_in=guard_in)
        return refus("upstream_unavailable", **meta)
    except Exception as exc:  # noqa: BLE001 — modèle indisponible, erreur inattendue
        logger.error(
            "[capacite] %s : %s: %s", cap.name, type(exc).__name__, str(exc)[:200]
        )
        await journaliser(
            "upstream_error" if _est_erreur_amont(exc) else "error", guard_in=guard_in
        )
        return refus("upstream_unavailable", **meta)

    texte = texte[: settings.mesagents_sortie_max_chars]
    guard_out = await capability_guard.io_sortie(
        db, texte, route=ctx.route, user_id=ctx.user.user_id, canary=canary
    )
    if guard_out == "blocked":
        await journaliser("guard_blocked", guard_in=guard_in, guard_out=guard_out)
        return refus("blocked_output", BLOCK_MESSAGE_OUTPUT, **meta)

    await journaliser("ok", guard_in=guard_in, guard_out=guard_out)
    return ResultatOutil(texte=texte, meta=meta)


def _est_erreur_amont(exc: Exception) -> bool:
    return isinstance(
        exc, (openai.APIError, openai.APIConnectionError)
    ) or _is_model_not_found(exc)


async def _executer_prompt(
    db,
    ctx: ContexteAppel,
    cap: Capability,
    forme,
    arguments: dict,
    canary: str,
    run_id: uuid.UUID,
) -> str:
    settings = get_settings()
    definition = forme.definition or {}
    declarees: dict[str, int] = {
        d["name"]: int(d["version"]) for d in (forme.dependencies or [])
    }
    outils: list[dict] = []
    for nom, numero in declarees.items():
        dep = await service.par_nom(db, nom)
        version_dep = service.version_numero(dep, numero) if dep is not None else None
        if dep is not None and version_dep is not None:
            outils.append(
                specification_outil(
                    nom, version_dep.description, version_dep.input_schema
                )
            )

    async def executeur(nom: str, args: dict) -> str:
        if (
            nom not in declarees
            or ctx.profondeur + 1 > settings.mesagents_profondeur_max
        ):
            await journal.ecrire(
                db,
                capability=nom if _SLUG.match(nom or "") else "?",
                capability_id=cap.id,
                version=None,
                hash=None,
                sub=ctx.user.user_id,
                azp=ctx.user.azp or "",
                scope_used="mesagents:read",
                guard_in="n/a",
                guard_out="n/a",
                ruleset_version=ruleset_version(),
                duration_ms=0,
                status="denied",
                route="dependency",
                parent_run_id=run_id,
            )
            return "dependency_not_allowed : cette capacité ne peut appeler que ses dépendances déclarées."
        enfant = ContexteAppel(
            user=ctx.user,
            jeton=ctx.jeton,
            route="dependency",
            parent_run_id=run_id,
            profondeur=ctx.profondeur + 1,
        )
        resultat = await executer(db, enfant, nom, declarees[nom], args)
        return (
            f"Erreur ({resultat.code}) : {resultat.texte}"
            if resultat.is_error
            else resultat.texte
        )

    modele = str(definition.get("model") or "") or settings.llm_default_model
    temperature = float(definition.get("temperature", 0.7))
    client = LlmClient()
    gabarit = str(definition.get("prompt") or "Tu es un assistant.")
    systeme = harden_system_prompt(gabarit, canary)
    user_text = texte_des_arguments(forme.input_schema or {}, arguments)
    try:
        return await arun_capability(
            client,
            system_prompt=systeme,
            user_text=user_text,
            tools=outils,
            model=modele,
            temperature=temperature,
            executeur=executeur,
        )
    except Exception as exc:
        if _is_model_not_found(exc) and modele != settings.llm_default_model:
            logger.warning(
                "[capacite] modèle %s introuvable, repli sur %s",
                modele,
                settings.llm_default_model,
            )
            return await arun_capability(
                client,
                system_prompt=systeme,
                user_text=user_text,
                tools=outils,
                model=settings.llm_default_model,
                temperature=temperature,
                executeur=executeur,
            )
        raise


async def _executer_relais(
    ctx: ContexteAppel, cap: Capability, forme, arguments: dict
) -> str:
    definition = forme.definition or {}
    autorisation = relais.autorisation_pour(definition, ctx.jeton)
    if cap.kind == "mcp":
        resultat = await relais.relayer_mcp(
            str(definition.get("endpoint", "")),
            str(definition.get("tool", "")),
            arguments,
            autorisation=autorisation,
            entetes=relais._entetes_declares(definition),
        )
    else:
        resultat = await relais.relayer_http(
            definition, arguments, autorisation=autorisation
        )
    if resultat.is_error:
        raise RelaisError(f"l'outil a répondu en erreur : {resultat.texte[:200]}")
    return resultat.texte


async def tester_brouillon(
    db: AsyncSession, ctx: ContexteAppel, cap: Capability, arguments: dict
) -> dict[str, Any]:
    """`POST /{id}/test` : verdict de garde sur la définition, puis exécution si favorable."""
    verdict = await capability_guard.verifier_definition(cap)
    corps: dict[str, Any] = {
        "result": None,
        "guard": {
            "verdict": verdict.verdict,
            "ruleset_version": verdict.ruleset_version,
            "details": verdict.details,
        },
        "guard_io": None,
    }
    if not verdict.favorable:
        return corps
    resultat = await executer(db, ctx, cap.name, None, arguments, brouillon=cap)
    if resultat.is_error:
        corps["error"] = {"code": resultat.code, "message": resultat.texte}
        corps["guard_io"] = {
            "entree": "blocked" if resultat.code == "blocked_input" else "ok",
            "sortie": "blocked"
            if resultat.code == "blocked_output"
            else ("n/a" if resultat.code == "blocked_input" else "ok"),
        }
        return corps
    corps["result"] = resultat.texte
    corps["guard_io"] = {"entree": "ok", "sortie": "ok"}
    return corps


__all__ = [
    "CapabilityVersion",
    "ContexteAppel",
    "ResultatOutil",
    "executer",
    "tester_brouillon",
    "valider_arguments",
]
