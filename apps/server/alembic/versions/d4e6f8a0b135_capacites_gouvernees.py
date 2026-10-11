"""capacités gouvernées (ADR Mes agents) : tables et copie des agents

Revision ID: d4e6f8a0b135
Revises: c3f5a7b9d124
Create Date: 2026-10-11 18:00:00.000000

Les agents existants deviennent des capacités `kind: prompt`, `grounding: open`,
`readOnlyHint: true` ; ceux qui étaient publiés ou soumis reçoivent une version 1 `alpha`,
hachée, au verdict de garde « migrated » (à requalifier par guard.recheck_all). Aucune donnée
n'est perdue : les tables `agents*` ne sont pas touchées, et le `downgrade` ne supprime que les
tables nouvelles. Idempotente : un agent déjà copié (`legacy_agent_id`) n'est pas recopié.
"""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d4e6f8a0b135"
down_revision: str | Sequence[str] | None = "c3f5a7b9d124"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TZ = sa.DateTime(timezone=True)


def _dans(colonne: str, valeurs: tuple[str, ...], nom: str) -> sa.CheckConstraint:
    liste = ", ".join(f"'{v}'" for v in valeurs)
    return sa.CheckConstraint(f"{colonne} IN ({liste})", name=nom)


def hash_canonique(
    definition: dict, input_schema: dict, dependencies: list[dict]
) -> str:
    """Copie FIGÉE de app.core.hashing.hash_canonique (un test vérifie l'égalité)."""
    charge = {
        "definition": definition,
        "input_schema": input_schema,
        "dependencies": sorted(
            (dict(d) for d in dependencies),
            key=lambda d: (str(d.get("name", "")), int(d.get("version", 0))),
        ),
    }
    octets = json.dumps(
        charge, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return hashlib.sha256(octets).hexdigest()


def slug(texte: str) -> str:
    ascii_ = (
        unicodedata.normalize("NFKD", texte or "").encode("ascii", "ignore").decode()
    )
    s = re.sub(r"[^a-z0-9]+", "-", ascii_.lower()).strip("-")[:60].strip("-")
    if len(s) < 3:
        s = (s + "-capacite").strip("-")
    if not re.match(r"^[a-z0-9]", s):
        s = "c" + s
    return s[:64]


SCHEMA_TEXTE = {
    "type": "object",
    "properties": {"text": {"type": "string", "description": "Le texte à traiter"}},
    "required": ["text"],
}
ANNOTATIONS = {
    "readOnlyHint": True,
    "destructiveHint": False,
    "idempotentHint": False,
    "openWorldHint": False,
}


def upgrade() -> None:
    op.create_table(
        "capabilities",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(64), nullable=False),
        sa.Column("kind", sa.String(8), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("description", sa.String(2000), nullable=False, server_default=""),
        sa.Column("input_schema", sa.JSON(), nullable=False),
        sa.Column("output_schema", sa.JSON(), nullable=True),
        sa.Column("definition", sa.JSON(), nullable=False),
        sa.Column("dependencies", sa.JSON(), nullable=False),
        sa.Column("grounding", sa.String(8), nullable=False),
        sa.Column("annotations", sa.JSON(), nullable=False),
        sa.Column("examples", sa.JSON(), nullable=False),
        sa.Column(
            "visibility", sa.String(16), nullable=False, server_default="private"
        ),
        sa.Column("community_path", sa.String(255), nullable=True),
        sa.Column("run_as", sa.String(16), nullable=False, server_default="user"),
        sa.Column("status", sa.String(16), nullable=False, server_default="draft"),
        sa.Column("current_version", sa.Integer(), nullable=True),
        sa.Column("owner_sub", sa.String(255), nullable=False),
        sa.Column("legacy_agent_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", _TZ, nullable=False),
        sa.Column("updated_at", _TZ, nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", name="uq_capabilities_name"),
        sa.UniqueConstraint("legacy_agent_id", name="uq_capabilities_legacy_agent_id"),
        _dans("kind", ("prompt", "mcp", "http"), "ck_capabilities_kind"),
        _dans("grounding", ("input", "open"), "ck_capabilities_grounding"),
        _dans(
            "visibility",
            ("private", "community", "ministry"),
            "ck_capabilities_visibility",
        ),
        _dans(
            "status",
            ("draft", "submitted", "published", "retired", "suspended"),
            "ck_capabilities_status",
        ),
    )
    op.create_index("ix_capabilities_name", "capabilities", ["name"], unique=True)
    op.create_index("ix_capabilities_status", "capabilities", ["status"])
    op.create_index("ix_capabilities_owner_sub", "capabilities", ["owner_sub"])

    op.create_table(
        "capability_versions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "capability_id", sa.Uuid(), sa.ForeignKey("capabilities.id"), nullable=False
        ),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("maturity", sa.String(8), nullable=False),
        sa.Column("hash", sa.String(64), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("description", sa.String(2000), nullable=False, server_default=""),
        sa.Column("definition", sa.JSON(), nullable=False),
        sa.Column("input_schema", sa.JSON(), nullable=False),
        sa.Column("output_schema", sa.JSON(), nullable=True),
        sa.Column("dependencies", sa.JSON(), nullable=False),
        sa.Column("annotations", sa.JSON(), nullable=False),
        sa.Column("grounding", sa.String(8), nullable=False),
        sa.Column("examples", sa.JSON(), nullable=False),
        sa.Column("published_by", sa.String(255), nullable=False),
        sa.Column("published_from", sa.String(255), nullable=False),
        sa.Column("published_at", _TZ, nullable=False),
        sa.Column("guard_verdict", sa.String(16), nullable=False),
        sa.Column("guard_ruleset_version", sa.String(32), nullable=False),
        sa.Column("guard_details", sa.JSON(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("capability_id", "version", name="uq_capability_version"),
        _dans(
            "maturity", ("alpha", "beta", "general"), "ck_capability_versions_maturity"
        ),
    )
    op.create_index(
        "ix_capability_versions_capability_id", "capability_versions", ["capability_id"]
    )
    op.create_index("ix_capability_versions_hash", "capability_versions", ["hash"])

    op.create_table(
        "runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("ts", _TZ, nullable=False),
        sa.Column("capability", sa.String(64), nullable=False),
        sa.Column("capability_id", sa.Uuid(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=True),
        sa.Column("hash", sa.String(64), nullable=True),
        sa.Column("sub", sa.String(255), nullable=False),
        sa.Column("azp", sa.String(255), nullable=False),
        sa.Column("scope_used", sa.String(32), nullable=False),
        sa.Column("guard_in", sa.String(16), nullable=False),
        sa.Column("guard_out", sa.String(16), nullable=False),
        sa.Column("ruleset_version", sa.String(32), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("route", sa.String(32), nullable=False),
        sa.Column("parent_run_id", sa.Uuid(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    for colonne in ("ts", "capability", "capability_id", "sub", "azp"):
        op.create_index(f"ix_runs_{colonne}", "runs", [colonne])

    op.create_table(
        "pins",
        sa.Column("sub", sa.String(255), nullable=False),
        sa.Column(
            "capability_id", sa.Uuid(), sa.ForeignKey("capabilities.id"), nullable=False
        ),
        sa.Column("rang", sa.Integer(), nullable=False),
        sa.Column("created_at", _TZ, nullable=False),
        sa.PrimaryKeyConstraint("sub", "capability_id"),
        sa.UniqueConstraint("sub", "rang", name="uq_pins_sub_rang"),
    )

    op.create_table(
        "suspended_clients",
        sa.Column("azp", sa.String(255), nullable=False),
        sa.Column("reason", sa.String(500), nullable=False, server_default=""),
        sa.Column("suspended_by", sa.String(255), nullable=False, server_default=""),
        sa.Column("suspended_at", _TZ, nullable=False),
        sa.PrimaryKeyConstraint("azp"),
    )

    _copier_les_agents()


def _copier_les_agents() -> None:
    """Chaque agent devient une capacité ; les publiés/soumis reçoivent une version 1 alpha."""
    bind = op.get_bind()
    agents = sa.table(
        "agents",
        sa.column("id", sa.Uuid()),
        sa.column("creator_id", sa.String()),
        sa.column("model_ref", sa.String()),
        sa.column("visibility", sa.String()),
        sa.column("status", sa.String()),
        sa.column("created_at", _TZ),
        sa.column("updated_at", _TZ),
    )
    versions = sa.table(
        "agent_versions",
        sa.column("agent_id", sa.Uuid()),
        sa.column("version", sa.Integer()),
        sa.column("config_snapshot", sa.JSON()),
    )
    capabilities = sa.table(
        "capabilities",
        sa.column("id", sa.Uuid()),
        sa.column("name", sa.String()),
        sa.column("kind", sa.String()),
        sa.column("title", sa.String()),
        sa.column("description", sa.String()),
        sa.column("input_schema", sa.JSON()),
        sa.column("output_schema", sa.JSON()),
        sa.column("definition", sa.JSON()),
        sa.column("dependencies", sa.JSON()),
        sa.column("grounding", sa.String()),
        sa.column("annotations", sa.JSON()),
        sa.column("examples", sa.JSON()),
        sa.column("visibility", sa.String()),
        sa.column("community_path", sa.String()),
        sa.column("run_as", sa.String()),
        sa.column("status", sa.String()),
        sa.column("current_version", sa.Integer()),
        sa.column("owner_sub", sa.String()),
        sa.column("legacy_agent_id", sa.Uuid()),
        sa.column("created_at", _TZ),
        sa.column("updated_at", _TZ),
    )
    capability_versions = sa.table(
        "capability_versions",
        sa.column("id", sa.Uuid()),
        sa.column("capability_id", sa.Uuid()),
        sa.column("version", sa.Integer()),
        sa.column("maturity", sa.String()),
        sa.column("hash", sa.String()),
        sa.column("title", sa.String()),
        sa.column("description", sa.String()),
        sa.column("definition", sa.JSON()),
        sa.column("input_schema", sa.JSON()),
        sa.column("output_schema", sa.JSON()),
        sa.column("dependencies", sa.JSON()),
        sa.column("annotations", sa.JSON()),
        sa.column("grounding", sa.String()),
        sa.column("examples", sa.JSON()),
        sa.column("published_by", sa.String()),
        sa.column("published_from", sa.String()),
        sa.column("published_at", _TZ),
        sa.column("guard_verdict", sa.String()),
        sa.column("guard_ruleset_version", sa.String()),
        sa.column("guard_details", sa.JSON()),
    )

    deja = {
        r[0]
        for r in bind.execute(
            sa.select(capabilities.c.legacy_agent_id).where(
                capabilities.c.legacy_agent_id.is_not(None)
            )
        )
    }
    noms_pris = {r[0] for r in bind.execute(sa.select(capabilities.c.name))}
    maintenant = datetime.now(UTC)

    for agent in bind.execute(
        sa.select(agents).order_by(agents.c.created_at, agents.c.id)
    ).mappings():
        if agent["id"] in deja:
            continue
        derniere = bind.execute(
            sa.select(versions.c.config_snapshot)
            .where(versions.c.agent_id == agent["id"])
            .order_by(versions.c.version.desc())
            .limit(1)
        ).scalar_one_or_none()
        snap = (
            derniere
            if isinstance(derniere, dict)
            else (json.loads(derniere) if derniere else {})
        )
        titre = str(snap.get("name") or "Agent sans nom")[:200]
        base = slug(titre)
        nom = base
        n = 2
        while nom in noms_pris:
            suffixe = f"-{n}"
            nom = base[: 64 - len(suffixe)] + suffixe
            n += 1
        noms_pris.add(nom)
        definition = {
            "prompt": str(snap.get("system_prompt") or "Tu es un assistant."),
            "model": str(snap.get("model_id") or agent["model_ref"] or ""),
            "temperature": float(snap.get("temperature", 0.7) or 0.7),
            "greeting": str(snap.get("greeting") or ""),
            "legacy": {
                "knowledge_ids": list(snap.get("knowledge_ids") or []),
                "tool_ids": list(snap.get("tool_ids") or []),
                "category": snap.get("category") or "",
            },
        }
        exemples = [
            {"input": {"text": str(e)}, "expected": None}
            for e in (snap.get("examples") or [])
            if str(e).strip()
        ][:20]
        statut_agent = str(agent["status"])
        if statut_agent in ("published", "submitted"):
            statut, numero = "published", 1
        elif statut_agent == "archived":
            statut, numero = "retired", None
        else:
            statut, numero = "draft", None
        cap_id = uuid.uuid4()
        bind.execute(
            capabilities.insert().values(
                id=cap_id,
                name=nom,
                kind="prompt",
                title=titre,
                description=str(snap.get("description") or "")[:2000],
                input_schema=SCHEMA_TEXTE,
                output_schema=None,
                definition=definition,
                dependencies=[],
                grounding="open",
                annotations=ANNOTATIONS,
                examples=exemples,
                visibility=str(agent["visibility"]),
                community_path=snap.get("community_path") or None,
                run_as="user",
                status=statut,
                current_version=numero,
                owner_sub=str(agent["creator_id"]),
                legacy_agent_id=agent["id"],
                created_at=agent["created_at"] or maintenant,
                updated_at=agent["updated_at"] or maintenant,
            )
        )
        if numero is not None:
            bind.execute(
                capability_versions.insert().values(
                    id=uuid.uuid4(),
                    capability_id=cap_id,
                    version=1,
                    maturity="alpha",
                    hash=hash_canonique(definition, SCHEMA_TEXTE, []),
                    title=titre,
                    description=str(snap.get("description") or "")[:2000],
                    definition=definition,
                    input_schema=SCHEMA_TEXTE,
                    output_schema=None,
                    dependencies=[],
                    annotations=ANNOTATIONS,
                    grounding="open",
                    examples=exemples,
                    published_by=str(agent["creator_id"]),
                    published_from="migration",
                    published_at=agent["updated_at"] or maintenant,
                    guard_verdict="migrated",
                    guard_ruleset_version="migration",
                    guard_details=[],
                )
            )


def downgrade() -> None:
    op.drop_table("pins")
    for colonne in ("ts", "capability", "capability_id", "sub", "azp"):
        op.drop_index(f"ix_runs_{colonne}", table_name="runs")
    op.drop_table("runs")
    op.drop_index("ix_capability_versions_hash", table_name="capability_versions")
    op.drop_index(
        "ix_capability_versions_capability_id", table_name="capability_versions"
    )
    op.drop_table("capability_versions")
    op.drop_index("ix_capabilities_owner_sub", table_name="capabilities")
    op.drop_index("ix_capabilities_status", table_name="capabilities")
    op.drop_index("ix_capabilities_name", table_name="capabilities")
    op.drop_table("capabilities")
    op.drop_table("suspended_clients")
