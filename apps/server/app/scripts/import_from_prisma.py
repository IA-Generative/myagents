"""Reprise des données de l'ancienne app Mes agents (Next.js + Prisma, tables ab_*).

Usage ::

    uv run python -m app.scripts.import_from_prisma --source-url postgresql://... [--dry-run]

La source peut aussi venir de la variable SOURCE_DATABASE_URL (évite le mot de passe dans
l'historique du shell). La cible est la DATABASE_URL de l'app, schéma Alembic à jour.

Garanties :
- source en lecture seule : sessions `default_transaction_read_only`, transaction READ ONLY
  en REPEATABLE READ (instantané cohérent entre les requêtes) ;
- idempotent : ids conservés, insertion seulement si absent ; un second passage n'insère rien ;
- cible écrite en une seule transaction (tout ou rien) ; `--dry-run` calcule et valide tout,
  lit la cible pour classer « déjà présent », n'écrit rien ;
- le bilan ne contient que des comptes : ni contenu de prompt, ni identifiant.

Correspondances :
- ab_agents → agents : id, visibility, category, tags, version, parent_agent_id, created_at,
  updated_at conservés ; creator_id = sub Keycloak (UUID en texte) ; statut `validated`
  → `published` ; model_ref = modelId de la dernière version, sinon LLM_DEFAULT_MODEL.
  Non repris : owui_model_id, creator_direction, quality_score.
- ab_agent_versions → agent_versions : id, agent_id, version, changelog, created_at conservés ;
  config_snapshot camelCase → ConfigSnapshot (knowledge_ids et tool_ids vides), tronqué
  aux bornes du schéma. Un agent dont la dernière version est inconvertible est rejeté.
- ab_ratings → ratings : champs identiques (commentaire tronqué à 1000 caractères).
- ab_favorites → favorites : id déterministe dérivé de (agent, utilisateur) ; created_at = date
  d'import (absente de la source) ; le dossier (`folder`) n'est pas repris.
- Non repris, seulement comptés : ab_usage_stats, ab_si_connectors, ab_conversations,
  ab_conversation_messages, ab_guard_events, ab_mail_indexes.

Procédure de bascule :
1. Geler les écritures de l'ancienne app (mise à l'échelle à 0 ou maintenance).
2. Sauvegarder source et cible : `pg_dump -Fc -t 'ab_*' <base source> > ab_avant_bascule.dump`
   et `pg_dump -Fc <base cible> > cible_avant_bascule.dump`.
3. Mettre la cible au schéma : `uv run alembic upgrade head`.
4. Dry-run : `... import_from_prisma --dry-run` ; lire les rejets et ajustements du bilan.
5. Import réel : même commande sans `--dry-run`.
6. Comptages : `SELECT count(*)` sur ab_agents / agents (etc.) ; lus = insérés + déjà présents
   + rejetés. Relancer l'import : il doit annoncer 0 inséré.
"""

import argparse
import asyncio
import json
import logging
import os
import sys
import uuid
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from pydantic import ValidationError
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.core.config import async_database_url, get_settings
from app.core.logging import setup_logging
from app.db.session import SessionLocal
from app.models.agent import Agent, AgentVersion, Favorite, Rating
from app.models.enums import AgentStatus, Visibility
from app.schemas.agent import MAX_PROMPT_CHARS, ConfigSnapshot

logger = logging.getLogger(__name__)

# Compte « Credentials » de dev local de l'ancienne app (apps/next/src/lib/auth.ts).
LEGACY_DEV_USER_ID = "00000000-0000-0000-0000-000000000001"
_FAVORITE_NAMESPACE = uuid.UUID("5b0e2f43-8c1d-4f6a-9e27-3d4c8a1b6f90")

TABLES = ("agents", "agent_versions", "ratings", "favorites")
SKIPPED_TABLES = (
    "ab_usage_stats",
    "ab_si_connectors",
    "ab_conversations",
    "ab_conversation_messages",
    "ab_guard_events",
    "ab_mail_indexes",
)

# Bornes du ConfigSnapshot (la validation Pydantic reste l'arbitre final).
_SNAPSHOT_TEXT_LIMITS = {
    "name": 200,
    "description": 2_000,
    "category": 255,
    "system_prompt": MAX_PROMPT_CHARS,
    "greeting": 2_000,
    "model_id": 255,
}
_COMMUNITY_PATH_MAX = 255
_EXAMPLES_MAX, _EXAMPLE_MAX_CHARS = 20, 500
# Clés camelCase écrites par l'ancienne app (api/ab/agents/route.ts, [id]/route.ts).
_SNAPSHOT_KEYS = {
    "name": "name",
    "description": "description",
    "category": "category",
    "systemPrompt": "system_prompt",
    "greeting": "greeting",
    "modelId": "model_id",
}
# `visibility` est portée par la colonne agents.visibility, pas par le snapshot.
_KNOWN_SNAPSHOT_KEYS = {
    *_SNAPSHOT_KEYS,
    "communityPath",
    "examples",
    "temperature",
    "visibility",
}
# Bornes des colonnes cible.
_LIST_MAX, _LIST_ITEM_MAX = 20, 255
_CHANGELOG_MAX, _COMMENT_MAX, _MODEL_REF_MAX = 500, 1_000, 255


class Rejected(Exception):
    """Ligne source impossible à reprendre ; `reason` ne contient aucune donnée."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass
class TableReport:
    read: int = 0
    inserted: int = 0
    existing: int = 0
    rejected: Counter[str] = field(default_factory=Counter)
    notes: Counter[str] = field(default_factory=Counter)


@dataclass
class ImportReport:
    dry_run: bool
    tables: dict[str, TableReport] = field(
        default_factory=lambda: {name: TableReport() for name in TABLES}
    )
    skipped: dict[str, int | None] = field(default_factory=dict)


@dataclass
class SourceData:
    """Lignes brutes des tables ab_* (dict par ligne, noms de colonnes SQL)."""

    agents: list[dict[str, Any]] = field(default_factory=list)
    versions: list[dict[str, Any]] = field(default_factory=list)
    ratings: list[dict[str, Any]] = field(default_factory=list)
    favorites: list[dict[str, Any]] = field(default_factory=list)
    skipped_counts: dict[str, int | None] = field(default_factory=dict)


@dataclass
class Plan:
    """Valeurs prêtes à insérer (constructeurs ORM), avant contrôle d'existence."""

    agents: list[dict[str, Any]] = field(default_factory=list)
    versions: list[dict[str, Any]] = field(default_factory=list)
    ratings: list[dict[str, Any]] = field(default_factory=list)
    favorites: list[dict[str, Any]] = field(default_factory=list)


# --- Conversion pure (sans I/O) ---


def _uuid(value: Any) -> uuid.UUID:
    if isinstance(value, uuid.UUID):
        return value
    try:
        return uuid.UUID(str(value))
    except (TypeError, ValueError) as exc:
        raise Rejected("identifiant non UUID") from exc


def _aware(value: Any, fallback: datetime) -> datetime:
    if not isinstance(value, datetime):
        return fallback
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def _text(value: Any, key: str, limit: int, notes: Counter[str]) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        notes[f"{key} : type inattendu, vidé"] += 1
        return ""
    if len(value) > limit:
        notes[f"{key} tronqué à {limit} caractères"] += 1
        return value[:limit]
    return value


def _str_list(
    value: Any, key: str, max_items: int, max_chars: int, notes: Counter[str]
) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        notes[f"{key} : type inattendu, vidé"] += 1
        return []
    items = [v for v in value if isinstance(v, str)]
    if len(items) < len(value):
        notes[f"{key} : élément non texte retiré"] += 1
    if len(items) > max_items:
        notes[f"{key} limité à {max_items} éléments"] += 1
        items = items[:max_items]
    if any(len(v) > max_chars for v in items):
        notes[f"{key} : élément tronqué à {max_chars} caractères"] += 1
        items = [v[:max_chars] for v in items]
    return items


def convert_snapshot(raw: Any, notes: Counter[str]) -> ConfigSnapshot:
    """Snapshot camelCase de l'ancienne app → ConfigSnapshot validé."""
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except ValueError as exc:
            raise Rejected("snapshot JSON illisible") from exc
    if not isinstance(raw, dict):
        raise Rejected("snapshot n'est pas un objet JSON")

    data: dict[str, Any] = {
        target: _text(raw.get(source), target, _SNAPSHOT_TEXT_LIMITS[target], notes)
        for source, target in _SNAPSHOT_KEYS.items()
    }
    data["community_path"] = (
        _text(raw.get("communityPath"), "community_path", _COMMUNITY_PATH_MAX, notes)
        or None
    )
    data["examples"] = _str_list(
        raw.get("examples"), "examples", _EXAMPLES_MAX, _EXAMPLE_MAX_CHARS, notes
    )

    temperature = raw.get("temperature")
    if temperature is None:
        temperature = 0.7
    elif isinstance(temperature, bool) or not isinstance(temperature, int | float):
        notes["temperature : type inattendu, 0.7 retenu"] += 1
        temperature = 0.7
    elif not 0 <= temperature <= 2:
        notes["temperature ramenée dans [0, 2]"] += 1
        temperature = min(max(temperature, 0), 2)
    data["temperature"] = float(temperature)
    # Pas de bases de connaissances ni d'outils dans l'ancienne app.
    data["knowledge_ids"] = []
    data["tool_ids"] = []

    unknown = set(raw) - _KNOWN_SNAPSHOT_KEYS
    if unknown:
        notes["clé de snapshot inconnue ignorée"] += len(unknown)
    if not data["name"]:
        notes["snapshot sans nom"] += 1
    if not data["model_id"]:
        notes["snapshot sans modelId"] += 1

    try:
        return ConfigSnapshot.model_validate(data)
    except ValidationError as exc:
        raise Rejected("snapshot invalide après conversion") from exc


def convert_version(raw: dict[str, Any], now: datetime, notes: Counter[str]) -> dict:
    snapshot = convert_snapshot(raw.get("config_snapshot"), notes)
    changelog = raw.get("changelog")
    if changelog is not None:
        changelog = _text(changelog, "changelog", _CHANGELOG_MAX, notes) or None
    return {
        "id": _uuid(raw["id"]),
        "agent_id": _uuid(raw["agent_id"]),
        "version": int(raw["version"]),
        "config_snapshot": snapshot.model_dump(),
        "changelog": changelog,
        "created_at": _aware(raw.get("created_at"), now),
    }


def convert_agent(
    raw: dict[str, Any],
    latest_snapshot: dict[str, Any] | None,
    default_model: str,
    now: datetime,
    notes: Counter[str],
) -> dict:
    """`latest_snapshot` : ConfigSnapshot (dump) de la dernière version, s'il y en a une."""
    try:
        visibility = Visibility(raw.get("visibility"))
    except ValueError as exc:
        raise Rejected("visibilité inconnue") from exc
    status_value = raw.get("status")
    if status_value == "validated":
        # Statut supprimé dans la nouvelle app : un agent validé est publié.
        notes["statut validated converti en published"] += 1
        status_value = AgentStatus.published.value
    try:
        status = AgentStatus(status_value)
    except ValueError as exc:
        raise Rejected("statut inconnu") from exc

    creator_id = str(_uuid(raw["creator_id"]))
    if creator_id == LEGACY_DEV_USER_ID:
        notes["créateur = compte de dev local de l'ancienne app"] += 1

    if latest_snapshot is None:
        notes["agent sans version"] += 1
    model_ref = (latest_snapshot or {}).get("model_id") or default_model
    if not (latest_snapshot or {}).get("model_id"):
        notes["model_ref = modèle par défaut (pas de modelId)"] += 1

    # Champs propres à l'ancienne app, sans équivalent dans le nouveau schéma.
    notes["owui_model_id non repris"] += 1
    if raw.get("creator_direction"):
        notes["creator_direction renseigné non repris"] += 1
    if raw.get("quality_score") is not None:
        notes["quality_score renseigné non repris"] += 1

    parent = raw.get("parent_agent_id")
    created_at = _aware(raw.get("created_at"), now)
    return {
        "id": _uuid(raw["id"]),
        "creator_id": creator_id,
        "model_ref": model_ref[:_MODEL_REF_MAX],
        "visibility": visibility,
        "status": status,
        "category": _str_list(
            raw.get("category"), "category", _LIST_MAX, _LIST_ITEM_MAX, notes
        ),
        "tags": _str_list(raw.get("tags"), "tags", _LIST_MAX, _LIST_ITEM_MAX, notes),
        "version": int(raw.get("version") or 1),
        "parent_agent_id": _uuid(parent) if parent is not None else None,
        "created_at": created_at,
        "updated_at": _aware(raw.get("updated_at"), created_at),
    }


def convert_rating(raw: dict[str, Any], now: datetime, notes: Counter[str]) -> dict:
    score = raw.get("score")
    if isinstance(score, bool) or not isinstance(score, int) or not 1 <= score <= 5:
        raise Rejected("note hors de 1 à 5")
    comment = raw.get("comment")
    if comment is not None:
        comment = _text(comment, "comment", _COMMENT_MAX, notes) or None
    return {
        "id": _uuid(raw["id"]),
        "agent_id": _uuid(raw["agent_id"]),
        "user_id": str(_uuid(raw["user_id"])),
        "score": score,
        "comment": comment,
        "created_at": _aware(raw.get("created_at"), now),
    }


def favorite_id(agent_id: uuid.UUID, user_id: str) -> uuid.UUID:
    # La source n'a pas d'id (clé primaire composite) : id déterministe pour l'idempotence.
    return uuid.uuid5(_FAVORITE_NAMESPACE, f"{agent_id}:{user_id}")


def convert_favorite(raw: dict[str, Any], now: datetime, notes: Counter[str]) -> dict:
    agent_id = _uuid(raw["agent_id"])
    user_id = str(_uuid(raw["user_id"]))
    notes["created_at absent de la source (date d'import)"] += 1
    if (raw.get("folder") or "default") != "default":
        notes["dossier de favori non repris"] += 1
    return {
        "id": favorite_id(agent_id, user_id),
        "agent_id": agent_id,
        "user_id": user_id,
        "created_at": now,
    }


@dataclass
class _ConvertedVersion:
    number: int
    values: dict | None
    reason: str | None
    notes: Counter[str]


def build_plan(
    source: SourceData, report: ImportReport, *, default_model: str, now: datetime
) -> Plan:
    """Convertit toutes les lignes source ; compte lus, rejets et ajustements."""
    plan = Plan()
    t_agents, t_versions, t_ratings, t_favorites = (report.tables[n] for n in TABLES)

    by_agent: dict[uuid.UUID, list[_ConvertedVersion]] = defaultdict(list)
    for raw in source.versions:
        t_versions.read += 1
        notes: Counter[str] = Counter()
        try:
            values, reason = convert_version(raw, now, notes), None
        except Rejected as exc:
            values, reason = None, exc.reason
        by_agent[_uuid(raw["agent_id"])].append(
            _ConvertedVersion(int(raw["version"]), values, reason, notes)
        )

    kept_agents: set[uuid.UUID] = set()
    for raw in source.agents:
        t_agents.read += 1
        agent_id = _uuid(raw["id"])
        versions = by_agent.pop(agent_id, [])
        latest = max(versions, key=lambda v: v.number, default=None)
        notes = Counter()
        try:
            if latest is not None and latest.values is None:
                # Sinon une version plus ancienne deviendrait silencieusement la courante.
                raise Rejected("dernière version inconvertible")
            snapshot = latest.values["config_snapshot"] if latest else None
            values = convert_agent(raw, snapshot, default_model, now, notes)
        except Rejected as exc:
            t_agents.rejected[exc.reason] += 1
            t_versions.rejected["agent rejeté"] += len(versions)
            continue
        if latest is not None and values["version"] != latest.number:
            notes["version de l'agent différente de sa dernière version"] += 1
        t_agents.notes.update(notes)
        plan.agents.append(values)
        kept_agents.add(agent_id)
        for version in versions:
            if version.values is None:
                t_versions.rejected[version.reason or "inconnue"] += 1
            else:
                t_versions.notes.update(version.notes)
                plan.versions.append(version.values)
    for versions in by_agent.values():
        t_versions.rejected["agent absent de la source"] += len(versions)

    for rows, table, convert, target in (
        (source.ratings, t_ratings, convert_rating, plan.ratings),
        (source.favorites, t_favorites, convert_favorite, plan.favorites),
    ):
        for raw in rows:
            table.read += 1
            notes = Counter()
            try:
                if _uuid(raw["agent_id"]) not in kept_agents:
                    raise Rejected("agent rejeté ou absent")
                values = convert(raw, now, notes)
            except Rejected as exc:
                table.rejected[exc.reason] += 1
                continue
            table.notes.update(notes)
            target.append(values)

    report.skipped = dict(source.skipped_counts)
    return plan


def _parents_first(agents: list[dict], notes: Counter[str]) -> list[dict]:
    """Ordonne les agents pour qu'un parent soit inséré avant ses dérivés."""
    pending = {a["id"]: a for a in agents}
    ordered: list[dict] = []
    while pending:
        ready = [
            a
            for a in pending.values()
            if a["parent_agent_id"] in (None, a["id"])
            or a["parent_agent_id"] not in pending
        ]
        if not ready:
            # Cycle de filiation : on coupe le lien plutôt que de bloquer l'import.
            notes["lien parent retiré (cycle)"] += len(pending)
            for a in pending.values():
                a["parent_agent_id"] = None
            ready = list(pending.values())
        for a in ready:
            ordered.append(pending.pop(a["id"]))
    return ordered


# --- I/O ---

_CHUNK = 5_000


async def _existing(db: AsyncSession, column, values: list) -> set:
    found: set = set()
    for i in range(0, len(values), _CHUNK):
        chunk = values[i : i + _CHUNK]
        found.update(
            (await db.execute(select(column).where(column.in_(chunk)))).scalars()
        )
    return found


async def _existing_pairs(db: AsyncSession, model, agent_ids: list) -> set:
    pairs: set = set()
    for i in range(0, len(agent_ids), _CHUNK):
        chunk = agent_ids[i : i + _CHUNK]
        rows = await db.execute(
            select(model.agent_id, model.user_id).where(model.agent_id.in_(chunk))
        )
        pairs.update((row.agent_id, row.user_id) for row in rows)
    return pairs


async def apply_plan(
    db: AsyncSession, plan: Plan, report: ImportReport, *, dry_run: bool
) -> None:
    """Insère ce qui manque en une transaction ; en dry-run, ne fait que compter."""
    t_agents, t_versions, t_ratings, t_favorites = (report.tables[n] for n in TABLES)

    existing_agents = await _existing(db, Agent.id, [a["id"] for a in plan.agents])
    new_agents = [a for a in plan.agents if a["id"] not in existing_agents]
    t_agents.existing = len(plan.agents) - len(new_agents)

    known = existing_agents | {a["id"] for a in new_agents}
    missing_parents = list(
        {a["parent_agent_id"] for a in new_agents if a["parent_agent_id"]} - known
    )
    known |= await _existing(db, Agent.id, missing_parents)
    for a in new_agents:
        if a["parent_agent_id"] and a["parent_agent_id"] not in known:
            t_agents.notes["lien parent retiré (parent introuvable)"] += 1
            a["parent_agent_id"] = None
    new_agents = _parents_first(new_agents, t_agents.notes)

    existing_versions = await _existing(
        db, AgentVersion.id, [v["id"] for v in plan.versions]
    )
    new_versions = [v for v in plan.versions if v["id"] not in existing_versions]
    t_versions.existing = len(plan.versions) - len(new_versions)
    late = sum(1 for v in new_versions if v["agent_id"] in existing_agents)
    if late:
        # L'agent déjà présent n'est pas mis à jour (insertion seulement si absent).
        t_versions.notes["version ajoutée à un agent déjà présent"] += late

    new_rows: dict[str, list[dict]] = {}
    for name, model, rows in (
        ("ratings", Rating, plan.ratings),
        ("favorites", Favorite, plan.favorites),
    ):
        ids = await _existing(db, model.id, [r["id"] for r in rows])
        pairs = await _existing_pairs(db, model, list({r["agent_id"] for r in rows}))
        # Unicité (agent, utilisateur) : une ligne déjà là sous un autre id compte aussi.
        new_rows[name] = [
            r
            for r in rows
            if r["id"] not in ids and (r["agent_id"], r["user_id"]) not in pairs
        ]
        report.tables[name].existing = len(rows) - len(new_rows[name])

    t_agents.inserted = len(new_agents)
    t_versions.inserted = len(new_versions)
    t_ratings.inserted = len(new_rows["ratings"])
    t_favorites.inserted = len(new_rows["favorites"])

    if dry_run:
        await db.rollback()
        return
    try:
        db.add_all(Agent(**a) for a in new_agents)
        db.add_all(AgentVersion(**v) for v in new_versions)
        db.add_all(Rating(**r) for r in new_rows["ratings"])
        db.add_all(Favorite(**f) for f in new_rows["favorites"])
        await db.commit()
    except Exception:
        await db.rollback()
        raise


async def import_source(
    db: AsyncSession,
    source: SourceData,
    *,
    dry_run: bool,
    default_model: str | None = None,
) -> ImportReport:
    report = ImportReport(dry_run=dry_run)
    plan = build_plan(
        source,
        report,
        default_model=default_model or get_settings().llm_default_model,
        now=datetime.now(UTC),
    )
    await apply_plan(db, plan, report, dry_run=dry_run)
    return report


_SOURCE_QUERIES = {
    "agents": (
        "SELECT id, owui_model_id, creator_id, creator_direction,"
        " visibility::text AS visibility, status::text AS status, category, tags,"
        " version, parent_agent_id, quality_score, created_at, updated_at"
        " FROM ab_agents ORDER BY created_at, id"
    ),
    "versions": (
        "SELECT id, agent_id, version, config_snapshot, changelog, created_at"
        " FROM ab_agent_versions ORDER BY agent_id, version"
    ),
    "ratings": (
        "SELECT id, agent_id, user_id, score, comment, created_at"
        " FROM ab_ratings ORDER BY created_at, id"
    ),
    "favorites": "SELECT user_id, agent_id, folder FROM ab_favorites ORDER BY agent_id, user_id",
}


async def read_source(source_url: str) -> SourceData:
    """Lit les tables ab_* dans une transaction en lecture seule."""
    url = async_database_url(source_url)
    if not url.startswith("postgresql+asyncpg://"):
        raise SystemExit("--source-url doit désigner une base PostgreSQL")
    engine = create_async_engine(
        url,
        # Toute écriture accidentelle est refusée par le serveur lui-même.
        connect_args={"server_settings": {"default_transaction_read_only": "on"}},
    )
    data = SourceData()
    try:
        async with engine.connect() as conn:
            await conn.execution_options(
                isolation_level="REPEATABLE READ", postgresql_readonly=True
            )
            # Une seule transaction (ouverte à la première requête), annulée à la fin.
            for name, query in _SOURCE_QUERIES.items():
                rows = (await conn.execute(text(query))).mappings().all()
                setattr(data, name, [dict(r) for r in rows])
            for table in SKIPPED_TABLES:
                present = (
                    await conn.execute(
                        text("SELECT to_regclass(:t)::text"), {"t": table}
                    )
                ).scalar()
                data.skipped_counts[table] = (
                    (
                        await conn.execute(text(f'SELECT count(*) FROM "{table}"'))
                    ).scalar()
                    if present
                    else None
                )
            await conn.rollback()
    finally:
        await engine.dispose()
    return data


def format_report(report: ImportReport) -> str:
    inserted = "à insérer" if report.dry_run else "insérés"
    lines = [
        "Reprise des données — "
        + ("DRY-RUN, rien n'est écrit" if report.dry_run else "import"),
        f"{'table':<16}{'lus':>8}{inserted:>12}{'déjà présents':>16}{'rejetés':>10}",
    ]
    for name, t in report.tables.items():
        lines.append(
            f"{name:<16}{t.read:>8}{t.inserted:>12}{t.existing:>16}{t.rejected.total():>10}"
        )
    for title, attr in (("Rejets", "rejected"), ("Ajustements", "notes")):
        entries = [
            f"  {name} : {count} × {reason}"
            for name, t in report.tables.items()
            for reason, count in sorted(getattr(t, attr).items())
        ]
        if entries:
            lines += [f"{title} :", *entries]
    if report.skipped:
        lines.append("Non repris (comptés) :")
        lines += [
            f"  {table} : " + ("table absente" if n is None else f"{n} ligne(s)")
            for table, n in report.skipped.items()
        ]
    return "\n".join(lines)


async def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Reprise des données de l'ancienne app (tables ab_*)."
    )
    parser.add_argument(
        "--source-url",
        default=os.environ.get("SOURCE_DATABASE_URL"),
        help="PostgreSQL de l'ancienne app (défaut : $SOURCE_DATABASE_URL)",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="tout calculer, ne rien écrire"
    )
    args = parser.parse_args(argv)
    if not args.source_url:
        parser.error("--source-url ou SOURCE_DATABASE_URL est requis")

    setup_logging()
    source = await read_source(args.source_url)
    async with SessionLocal() as db:
        report = await import_source(db, source, dry_run=args.dry_run)
    print(format_report(report))
    logger.info("reprise terminée (%s)", "dry-run" if args.dry_run else "écrite")


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1:]))
