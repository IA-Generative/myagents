"""Cycle de vie des capacités (ADR §4.5, §10.1 point 3) : créer, modifier un brouillon, publier,
retirer, lire, lister — et la forme publiée servie à `tools/list` et à `GET /capabilities`."""

from __future__ import annotations

import logging
import uuid
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import get_settings
from app.core.contrat import ContratError
from app.core.hashing import hash_canonique
from app.core.portees import Operation, exiger
from app.mcp import notifications
from app.models.capability import Capability, CapabilityVersion
from app.schemas.capability import (
    ANNOTATIONS_DEFAUT_OUTIL,
    ANNOTATIONS_DEFAUT_PROMPT,
    CapabilityCreate,
    CapabilityPatch,
    PublishRequest,
    valider_definition,
    valider_schema,
)
from app.services import capability_guard, dependances, journal, pins
from app.services.visibilite import est_servie, visible_pour

logger = logging.getLogger(__name__)

_IMMUABLES = ("published", "retired", "suspended")


# --- Lecture -----------------------------------------------------------------------------------


def _avec_versions(stmt):
    return stmt.options(selectinload(Capability.versions))


async def obtenir(db: AsyncSession, cap_id: uuid.UUID) -> Capability | None:
    stmt = _avec_versions(select(Capability).where(Capability.id == cap_id))
    return (await db.execute(stmt)).scalar_one_or_none()


async def par_nom(db: AsyncSession, name: str) -> Capability | None:
    stmt = _avec_versions(select(Capability).where(Capability.name == name))
    return (await db.execute(stmt)).scalar_one_or_none()


def version_numero(cap: Capability, numero: int | None) -> CapabilityVersion | None:
    for v in cap.versions:
        if v.version == numero:
            return v
    return None


async def version_servie(db: AsyncSession, cap: Capability) -> CapabilityVersion | None:
    if cap.current_version is None:
        return None
    # Toujours une requête : la relation `versions` peut ne pas être chargée (asynchrone).
    stmt = select(CapabilityVersion).where(
        CapabilityVersion.capability_id == cap.id,
        CapabilityVersion.version == cap.current_version,
    )
    return (await db.execute(stmt)).scalar_one_or_none()


async def visible(db: AsyncSession, cap: Capability | None, user) -> bool:
    if cap is None:
        return False
    return visible_pour(cap, await version_servie(db, cap), user)


async def lister_visibles(db: AsyncSession, user) -> list[Capability]:
    """Toutes les capacités que la personne peut voir : les siennes, et celles servies pour elle."""
    stmt = _avec_versions(
        select(Capability)
        .where(
            or_(
                Capability.owner_sub == user.user_id,
                Capability.current_version.is_not(None),
            )
        )
        .order_by(Capability.updated_at.desc())
    )
    caps = list((await db.execute(stmt)).scalars().all())
    return [
        c for c in caps if visible_pour(c, version_numero(c, c.current_version), user)
    ]


async def rechercher(
    db: AsyncSession, user, texte: str, limite: int
) -> list[Capability]:
    """Recherche lexicale (nom, titre, description) parmi les capacités servies et visibles."""
    mots = [m.lower() for m in texte.split() if m.strip()]
    servies = [c for c in await lister_visibles(db, user) if est_servie(c)]
    if not mots:
        return servies[:limite]

    def score(c: Capability) -> int:
        corpus = f"{c.name} {c.title} {c.description}".lower()
        return sum(
            (3 if m in c.name.lower() else 0)
            + (2 if m in c.title.lower() else 0)
            + (1 if m in corpus else 0)
            for m in mots
        )

    classees = sorted(((score(c), c) for c in servies), key=lambda t: -t[0])
    return [c for s, c in classees if s > 0][:limite]


# --- Formes servies ----------------------------------------------------------------------------


def _description_servie(description: str, maturity: str) -> str:
    return f"[bêta] {description}" if maturity == "beta" else description


def forme_outil(cap: Capability, version: CapabilityVersion | None) -> dict[str, Any]:
    """La définition d'outil MCP (forme publiée) ; un brouillon sans version reprend sa fiche."""
    source = version if version is not None else cap
    maturity = version.maturity if version is not None else None
    return {
        "name": cap.name,
        "title": source.title,
        "description": _description_servie(source.description, maturity or ""),
        "inputSchema": source.input_schema,
        "annotations": source.annotations or {},
        "_meta": {
            "hash": version.hash if version is not None else None,
            "version": version.version if version is not None else None,
            "maturity": maturity,
            "grounding": source.grounding,
        },
    }


def forme_gestion(
    cap: Capability, version: CapabilityVersion | None, *, epinglee: bool = False
) -> dict[str, Any]:
    """Forme de `GET /capabilities` : celle de tools/list, plus l'état pour les écrans."""
    return {
        **forme_outil(cap, version),
        "id": str(cap.id),
        "kind": cap.kind,
        "status": cap.status,
        "visibility": cap.visibility,
        "community_path": cap.community_path,
        "owner_sub": cap.owner_sub,
        "current_version": cap.current_version,
        "grounding": cap.grounding,
        "updated_at": cap.updated_at.isoformat() if cap.updated_at else None,
        "pinned": epinglee,
    }


def _forme_version(v: CapabilityVersion) -> dict[str, Any]:
    return {
        "version": v.version,
        "maturity": v.maturity,
        "hash": v.hash,
        "published_by": v.published_by,
        "published_from": v.published_from,
        "published_at": v.published_at.isoformat() if v.published_at else None,
        "annotations": v.annotations,
        "guard": {
            "verdict": v.guard_verdict,
            "ruleset_version": v.guard_ruleset_version,
            "details": v.guard_details or [],
        },
    }


def detail(
    cap: Capability, version: CapabilityVersion | None, user, *, epinglee: bool = False
) -> dict[str, Any]:
    corps = forme_gestion(cap, version, epinglee=epinglee)
    corps.update(
        {
            "title": cap.title,
            "description": cap.description,
            "input_schema": cap.input_schema,
            "output_schema": cap.output_schema,
            "dependencies": cap.dependencies,
            "examples": cap.examples,
            "annotations": cap.annotations,
            "run_as": cap.run_as,
            "versions": [
                _forme_version(v)
                for v in sorted(cap.versions, key=lambda v: -v.version)
            ],
        }
    )
    if cap.owner_sub == user.user_id or user.is_reviewer:
        corps["definition"] = cap.definition
    return corps


# --- Annotations -------------------------------------------------------------------------------


def _annotations_declarees(
    kind: str, declarees: dict | None, dependencies: list
) -> dict[str, Any]:
    if kind == "prompt":
        base = dict(ANNOTATIONS_DEFAUT_PROMPT)
        if not dependencies:
            # Un prompt sans dépendance ne touche à rien : lecture seule, nécessairement.
            return base
        base.update({k: v for k, v in (declarees or {}).items() if v is not None})
        return base
    base = dict(ANNOTATIONS_DEFAUT_OUTIL)
    base.update({k: v for k, v in (declarees or {}).items() if v is not None})
    return base


def heriter_annotations(
    propres: dict[str, Any], des_dependances: list[dict[str, Any]]
) -> dict[str, Any]:
    """Un prompt hérite des annotations les plus défavorables de ses dépendances (ADR §4.1 bis)."""
    if not des_dependances:
        return propres
    return {
        "readOnlyHint": bool(propres.get("readOnlyHint", True))
        and all(d.get("readOnlyHint", False) for d in des_dependances),
        "destructiveHint": bool(propres.get("destructiveHint", False))
        or any(d.get("destructiveHint", True) for d in des_dependances),
        "idempotentHint": bool(propres.get("idempotentHint", False))
        and all(d.get("idempotentHint", False) for d in des_dependances),
        "openWorldHint": bool(propres.get("openWorldHint", False))
        or any(d.get("openWorldHint", True) for d in des_dependances),
    }


def lecture_seule(annotations: dict[str, Any]) -> bool:
    return bool(annotations.get("readOnlyHint", False))


# --- Écriture ----------------------------------------------------------------------------------


async def creer(db: AsyncSession, user, payload: CapabilityCreate) -> Capability:
    if await par_nom(db, payload.name) is not None:
        raise ContratError(
            400, "invalid_request", f"le nom « {payload.name} » est déjà pris"
        )
    deps = [d.model_dump() for d in payload.dependencies]
    cap = Capability(
        name=payload.name,
        kind=payload.kind,
        title=payload.title,
        description=payload.description,
        input_schema=payload.input_schema,
        output_schema=payload.output_schema,
        definition=payload.definition,
        dependencies=deps,
        grounding=payload.grounding,
        annotations=_annotations_declarees(
            payload.kind,
            payload.annotations.model_dump() if payload.annotations else None,
            deps,
        ),
        examples=[e.model_dump() for e in payload.examples],
        visibility=payload.visibility,
        community_path=payload.community_path,
        run_as=payload.run_as,
        status="draft",
        owner_sub=user.user_id,
    )
    db.add(cap)
    await db.commit()
    return await obtenir(db, cap.id)


async def modifier(
    db: AsyncSession, cap: Capability, patch: CapabilityPatch
) -> Capability:
    if cap.status in _IMMUABLES:
        raise ContratError.de("immutable_version")
    champs = patch.model_dump(exclude_unset=True)
    if "definition" in champs and champs["definition"] is not None:
        try:
            champs["definition"] = valider_definition(cap.kind, champs["definition"])
        except ValueError as exc:
            raise ContratError(400, "invalid_request", str(exc)) from exc
    if "input_schema" in champs and champs["input_schema"] is not None:
        try:
            champs["input_schema"] = valider_schema(champs["input_schema"])
        except ValueError as exc:
            raise ContratError(400, "invalid_request", str(exc)) from exc
    if "dependencies" in champs and champs["dependencies"] is not None:
        champs["dependencies"] = [
            d if isinstance(d, dict) else d.model_dump() for d in champs["dependencies"]
        ]
    if "examples" in champs and champs["examples"] is not None:
        champs["examples"] = [
            e if isinstance(e, dict) else e.model_dump() for e in champs["examples"]
        ]
    annotations = champs.pop("annotations", None)
    for nom, valeur in champs.items():
        setattr(cap, nom, valeur)
    cap.annotations = _annotations_declarees(
        cap.kind,
        annotations if annotations is not None else cap.annotations,
        cap.dependencies,
    )
    if cap.visibility == "community" and not (cap.community_path or "").strip():
        raise ContratError(
            400,
            "invalid_request",
            "community_path est requis pour la visibilité community",
        )
    cap.status = (
        "draft"  # une capacité soumise que l'auteur retouche revient en brouillon
    )
    await db.commit()
    return await obtenir(db, cap.id)


async def ouvrir_brouillon(db: AsyncSession, cap: Capability) -> Capability:
    """Modifier une capacité publiée crée un brouillon ; la version publiée reste servie."""
    if cap.status != "draft":
        cap.status = "draft"
        await db.commit()
    return await obtenir(db, cap.id)


def _droits_de_publication(cap: Capability, user) -> None:
    """Droit de la personne, puis portée du client (ordre du §10.1 point 3)."""
    if cap.owner_sub == user.user_id:
        exiger(user.scopes, Operation.REDIGER)
        return
    if cap.status != "submitted":
        raise ContratError.de("not_found")
    exiger(user.scopes, Operation.REVOIR)
    if not user.is_reviewer:
        raise ContratError(
            403,
            "forbidden",
            "la publication d'une capacité soumise exige le rôle mesagents-reviewer",
        )


def _peut_revoir(user) -> bool:
    return user.is_reviewer and "mesagents:review" in user.scopes


async def publier(
    db: AsyncSession, user, cap: Capability, demande: PublishRequest
) -> Capability:
    _droits_de_publication(cap, user)
    if cap.status in _IMMUABLES:
        raise ContratError.de(
            "immutable_version",
            "cette capacité est déjà publiée : ouvrez un brouillon (POST …/draft) pour la modifier",
        )
    visibility = demande.visibility or cap.visibility
    community_path = (
        demande.community_path
        if demande.community_path is not None
        else cap.community_path
    )
    if visibility == "community" and not (community_path or "").strip():
        raise ContratError(
            400,
            "invalid_request",
            "community_path est requis pour la visibilité community",
        )
    if cap.grounding == "open" and len(cap.examples or []) < 3:
        raise ContratError(
            422,
            "invalid_request",
            "une capacité générative (grounding: open) se publie avec au moins trois exemples attendus",
        )

    verdict = await capability_guard.verifier_definition(cap)
    if verdict.indisponible:
        raise ContratError(
            502,
            "upstream_unavailable",
            "la garde n'a pas pu rendre de verdict (modèle juge indisponible) : rien n'est publié, réessayez",
            details=verdict.details,
        )
    if not verdict.favorable:
        raise ContratError(422, "guard_rejected", details=verdict.details)

    raisons = await dependances.verifier_dependances(
        db, cap.dependencies, demande.maturity, user
    )
    if raisons:
        raise ContratError(422, "dependency_not_allowed", details=raisons)

    annotations_deps = []
    for dep in cap.dependencies:
        _, version_dep = await dependances.resoudre(db, dep["name"], dep["version"])
        if version_dep is not None:
            annotations_deps.append(version_dep.annotations or {})
    effectives = (
        heriter_annotations(cap.annotations or {}, annotations_deps)
        if cap.kind == "prompt"
        else dict(cap.annotations or {})
    )

    # Revue requise : visibilité ministère, ou capacité non lecture seule (quelle que soit la visibilité).
    revue_requise = visibility == "ministry" or not lecture_seule(effectives)
    if revue_requise and not _peut_revoir(user):
        cap.status = "submitted"
        cap.visibility = visibility
        cap.community_path = community_path
        cap.annotations = effectives
        await db.commit()
        return await obtenir(db, cap.id)

    numero = (cap.current_version or 0) + 1
    version = CapabilityVersion(
        capability_id=cap.id,
        version=numero,
        maturity=demande.maturity,
        hash=hash_canonique(cap.definition, cap.input_schema, cap.dependencies),
        title=cap.title,
        description=cap.description,
        definition=cap.definition,
        input_schema=cap.input_schema,
        output_schema=cap.output_schema,
        dependencies=cap.dependencies,
        annotations=effectives,
        grounding=cap.grounding,
        examples=cap.examples,
        published_by=user.user_id,
        published_from=user.azp or "",
        guard_verdict=verdict.verdict,
        guard_ruleset_version=verdict.ruleset_version,
        guard_details=verdict.details,
    )
    db.add(version)
    cap.status = "published"
    cap.current_version = numero
    cap.visibility = visibility
    cap.community_path = community_path
    cap.annotations = effectives
    await db.commit()
    await db.refresh(cap, attribute_names=["versions"])
    notifications.diffuseur.notifier_list_changed(None)
    return await obtenir(db, cap.id)


async def dependants_de(db: AsyncSession, name: str) -> list[Capability]:
    stmt = _avec_versions(
        select(Capability).where(Capability.current_version.is_not(None))
    )
    caps = list((await db.execute(stmt)).scalars().all())
    return [
        c
        for c in caps
        if c.status not in ("retired", "suspended")
        and any(d.get("name") == name for d in (c.dependencies or []))
    ]


async def retirer(
    db: AsyncSession, user, cap: Capability, *, motif: str = "retire"
) -> Capability:
    """Retire la version servie ; les dépendants passent à `suspended` et sont notifiés."""
    if cap.status == "retired":
        return cap
    if cap.owner_sub != user.user_id and not _peut_revoir(user):
        if "mesagents:review" not in user.scopes and cap.owner_sub != user.user_id:
            raise ContratError(
                403,
                "forbidden",
                "retirer la capacité d'un autre exige la portée mesagents:review et le rôle mesagents-reviewer",
            )
        raise ContratError(
            403,
            "forbidden",
            "retirer la capacité d'un autre exige le rôle mesagents-reviewer",
        )
    if cap.owner_sub == user.user_id and not _peut_revoir(user):
        exiger(user.scopes, Operation.REDIGER)
    cap.status = "retired"
    await db.commit()
    a_prevenir: set[str] = set(await pins.abonnes_de(db, cap))
    for dep in await dependants_de(db, cap.name):
        dep.status = "suspended"
        await db.commit()
        a_prevenir.update(await pins.abonnes_de(db, dep))
        a_prevenir.add(dep.owner_sub)
        await journal.ecrire(
            db,
            capability=dep.name,
            capability_id=dep.id,
            version=dep.current_version,
            hash=None,
            sub=user.user_id,
            azp=user.azp or "",
            scope_used="mesagents:review"
            if cap.owner_sub != user.user_id
            else "mesagents:author",
            guard_in="n/a",
            guard_out="n/a",
            ruleset_version="",
            duration_ms=0,
            status="suspended",
            route=motif,
        )
    notifications.diffuseur.notifier_list_changed(None)
    logger.info(
        "[capacites] %s retirée (%s), %d dépendant(s) suspendu(s)",
        cap.name,
        motif,
        len(a_prevenir),
    )
    return await obtenir(db, cap.id)


def plafond_epingles() -> int:
    return get_settings().mesagents_epingles_max
