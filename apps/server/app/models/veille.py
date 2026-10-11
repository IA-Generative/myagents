"""ORM des veilles (chantier 3) : planification, exécutions par créneau, résultats dans l'espace
de la personne. Minimisation : seuls les champs nécessaires (sujet, sources, fréquence, résultats)."""

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


def _utcnow() -> datetime:
    return datetime.now(UTC)


_TZ = DateTime(timezone=True)


class Schedule(Base):
    __tablename__ = "schedules"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    sub: Mapped[str] = mapped_column(String(255), index=True)
    capability_name: Mapped[str] = mapped_column(String(64))
    sujet: Mapped[str] = mapped_column(String(200))
    sources: Mapped[list[str]] = mapped_column(JSON, default=list)
    cron: Mapped[str] = mapped_column(String(64))
    actif: Mapped[bool] = mapped_column(Boolean, default=True)
    conservation_jours: Mapped[int] = mapped_column(Integer, default=90)
    derniere_execution: Mapped[datetime | None] = mapped_column(_TZ, nullable=True)
    created_at: Mapped[datetime] = mapped_column(_TZ, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(_TZ, default=_utcnow, onupdate=_utcnow)


class ScheduleRun(Base):
    """Une ligne par (veille, créneau) : l'unicité interdit deux exécutions sur le même créneau."""

    __tablename__ = "schedule_runs"
    __table_args__ = (
        UniqueConstraint("schedule_id", "slot", name="uq_schedule_runs_slot"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    schedule_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("schedules.id"), index=True
    )
    slot: Mapped[datetime] = mapped_column(_TZ)
    status: Mapped[str] = mapped_column(String(24), default="en_cours")
    result_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    run_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(_TZ, default=_utcnow)


class VeilleResultat(Base):
    __tablename__ = "veille_resultats"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    schedule_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("schedules.id"), index=True
    )
    sub: Mapped[str] = mapped_column(String(255), index=True)
    synthese: Mapped[str] = mapped_column(Text)
    generated: Mapped[bool] = mapped_column(Boolean, default=True)
    sources: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    urls_consultees: Mapped[list[str]] = mapped_column(JSON, default=list)
    run_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(_TZ, default=_utcnow, index=True)
    expires_at: Mapped[datetime] = mapped_column(_TZ, index=True)
