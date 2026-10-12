"""ORM : capacités gouvernées (ADR Mes agents §4, §10.1 point 1).

- `capabilities` : la fiche de travail (brouillon) et l'état ;
- `capability_versions` : la forme PUBLIÉE, figée et hachée — aucune mise à jour possible
  (un écouteur ORM lève `ImmutableVersionError`, aucune route n'y touche) ;
- `runs` : le journal des exécutions (jamais de contenu) ;
- `pins` : les capacités épinglées par une personne ;
- `suspended_clients` : les `azp` suspendus, lus à chaque appel.

Colonnes `String` + contraintes CHECK plutôt que des types ENUM : les tests tournent sur SQLite,
la production sur PostgreSQL, et une valeur nouvelle ne doit pas exiger une migration de type.
"""

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    event,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

KINDS = ("prompt", "mcp", "http")
GROUNDINGS = ("input", "open")
MATURITIES = ("alpha", "beta", "general")
VISIBILITIES = ("private", "community", "ministry")
STATUTS = ("draft", "submitted", "published", "retired", "suspended")
RUN_STATUTS = (
    "ok",
    "denied",
    "guard_blocked",
    "not_found",
    "scope_missing",
    "invalid_request",
    "rate_limited",
    "upstream_error",
    "error",
    "suspended",
)


def _utcnow() -> datetime:
    return datetime.now(UTC)


_TZ = DateTime(timezone=True)


def _dans(colonne: str, valeurs: tuple[str, ...], nom: str) -> CheckConstraint:
    liste = ", ".join(f"'{v}'" for v in valeurs)
    return CheckConstraint(f"{colonne} IN ({liste})", name=nom)


class ImmutableVersionError(RuntimeError):
    """Tentative de modification d'une version publiée (règle 2 de l'ADR)."""


class Capability(Base):
    __tablename__ = "capabilities"
    __table_args__ = (
        _dans("kind", KINDS, "ck_capabilities_kind"),
        _dans("grounding", GROUNDINGS, "ck_capabilities_grounding"),
        _dans("visibility", VISIBILITIES, "ck_capabilities_visibility"),
        _dans("status", STATUTS, "ck_capabilities_status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    kind: Mapped[str] = mapped_column(String(8))
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(String(2000), default="")
    input_schema: Mapped[dict[str, Any]] = mapped_column(JSON)
    output_schema: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    definition: Mapped[dict[str, Any]] = mapped_column(JSON)
    dependencies: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    grounding: Mapped[str] = mapped_column(String(8))
    annotations: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    examples: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    visibility: Mapped[str] = mapped_column(String(16), default="private")
    community_path: Mapped[str | None] = mapped_column(String(255), nullable=True)
    run_as: Mapped[str] = mapped_column(String(16), default="user")
    status: Mapped[str] = mapped_column(String(16), default="draft", index=True)
    # Version servie (tools/list, exécution) ; None tant que rien n'est publié.
    current_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    owner_sub: Mapped[str] = mapped_column(String(255), index=True)
    # Agent de l'ancien modèle dont cette capacité est la copie (migration idempotente).
    legacy_agent_id: Mapped[uuid.UUID | None] = mapped_column(
        nullable=True, unique=True
    )
    created_at: Mapped[datetime] = mapped_column(_TZ, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(_TZ, default=_utcnow, onupdate=_utcnow)

    versions: Mapped[list[CapabilityVersion]] = relationship(
        back_populates="capability",
        order_by="desc(CapabilityVersion.version)",
        cascade="all, delete-orphan",
    )


class CapabilityVersion(Base):
    """Forme publiée d'une capacité : immuable, hachée, avec sa provenance et son verdict."""

    __tablename__ = "capability_versions"
    __table_args__ = (
        UniqueConstraint("capability_id", "version", name="uq_capability_version"),
        _dans("maturity", MATURITIES, "ck_capability_versions_maturity"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    capability_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("capabilities.id"), index=True
    )
    version: Mapped[int] = mapped_column(Integer)
    maturity: Mapped[str] = mapped_column(String(8))
    hash: Mapped[str] = mapped_column(String(64), index=True)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(String(2000), default="")
    definition: Mapped[dict[str, Any]] = mapped_column(JSON)
    input_schema: Mapped[dict[str, Any]] = mapped_column(JSON)
    output_schema: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    dependencies: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    annotations: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    grounding: Mapped[str] = mapped_column(String(8))
    examples: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    published_by: Mapped[str] = mapped_column(String(255))
    published_from: Mapped[str] = mapped_column(String(255))
    published_at: Mapped[datetime] = mapped_column(_TZ, default=_utcnow)
    guard_verdict: Mapped[str] = mapped_column(String(16))
    guard_ruleset_version: Mapped[str] = mapped_column(String(32))
    guard_details: Mapped[list[str]] = mapped_column(JSON, default=list)

    capability: Mapped[Capability] = relationship(back_populates="versions")


@event.listens_for(CapabilityVersion, "before_update")
def _refuser_la_mise_a_jour(mapper, connection, target) -> None:
    raise ImmutableVersionError(
        f"version {target.version} de la capacité {target.capability_id} : immuable"
    )


class Run(Base):
    """Une ligne par appel (règle 6). Aucune colonne de contenu, d'arguments ni de résultat."""

    __tablename__ = "runs"
    __table_args__ = (_dans("status", RUN_STATUTS, "ck_runs_status"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    ts: Mapped[datetime] = mapped_column(_TZ, default=_utcnow, index=True)
    capability: Mapped[str] = mapped_column(String(64), index=True)
    capability_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True, index=True)
    version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    sub: Mapped[str] = mapped_column(String(255), index=True)
    azp: Mapped[str] = mapped_column(String(255), index=True)
    scope_used: Mapped[str] = mapped_column(String(32))
    guard_in: Mapped[str] = mapped_column(String(16))
    guard_out: Mapped[str] = mapped_column(String(16))
    ruleset_version: Mapped[str] = mapped_column(String(32))
    duration_ms: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(24))
    route: Mapped[str] = mapped_column(String(32))
    parent_run_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)


class Pin(Base):
    __tablename__ = "pins"
    __table_args__ = (UniqueConstraint("sub", "rang", name="uq_pins_sub_rang"),)

    sub: Mapped[str] = mapped_column(String(255), primary_key=True)
    capability_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("capabilities.id"), primary_key=True
    )
    rang: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(_TZ, default=_utcnow)


class SuspendedClient(Base):
    __tablename__ = "suspended_clients"

    azp: Mapped[str] = mapped_column(String(255), primary_key=True)
    reason: Mapped[str] = mapped_column(String(500), default="")
    suspended_by: Mapped[str] = mapped_column(String(255), default="")
    suspended_at: Mapped[datetime] = mapped_column(_TZ, default=_utcnow)
