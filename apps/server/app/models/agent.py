"""ORM models: Agent, AgentVersion, Rating, Favorite."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import JSON, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import AgentStatus, Visibility


def _utcnow() -> datetime:
    return datetime.now(UTC)


_TZ = DateTime(timezone=True)


class Agent(Base):
    __tablename__ = "agents"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    creator_id: Mapped[str] = mapped_column(String(255), index=True)
    # Reference to the model served by the LLM adapter (e.g. "gpt-oss-120b").
    model_ref: Mapped[str] = mapped_column(String(255))
    visibility: Mapped[Visibility] = mapped_column(default=Visibility.private)
    status: Mapped[AgentStatus] = mapped_column(default=AgentStatus.draft)
    category: Mapped[list[str]] = mapped_column(JSON, default=list)
    tags: Mapped[list[str]] = mapped_column(JSON, default=list)
    version: Mapped[int] = mapped_column(default=1)
    parent_agent_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("agents.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(_TZ, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(_TZ, default=_utcnow, onupdate=_utcnow)

    versions: Mapped[list[AgentVersion]] = relationship(
        back_populates="agent",
        order_by="desc(AgentVersion.version)",
        cascade="all, delete-orphan",
    )
    ratings: Mapped[list[Rating]] = relationship(
        back_populates="agent", cascade="all, delete-orphan"
    )
    favorites: Mapped[list[Favorite]] = relationship(
        back_populates="agent", cascade="all, delete-orphan"
    )


class AgentVersion(Base):
    __tablename__ = "agent_versions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    agent_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("agents.id"))
    version: Mapped[int]
    # Full wizard draft (name, description, systemPrompt, greeting, examples...).
    config_snapshot: Mapped[dict] = mapped_column(JSON)
    changelog: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(_TZ, default=_utcnow)

    agent: Mapped[Agent] = relationship(back_populates="versions")


class Rating(Base):
    __tablename__ = "ratings"
    __table_args__ = (
        UniqueConstraint("agent_id", "user_id", name="uq_rating_agent_user"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    agent_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("agents.id"))
    user_id: Mapped[str] = mapped_column(String(255))
    score: Mapped[int]
    comment: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    created_at: Mapped[datetime] = mapped_column(_TZ, default=_utcnow)

    agent: Mapped[Agent] = relationship(back_populates="ratings")


class Favorite(Base):
    __tablename__ = "favorites"
    __table_args__ = (
        UniqueConstraint("agent_id", "user_id", name="uq_favorite_agent_user"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    agent_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("agents.id"))
    user_id: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(_TZ, default=_utcnow)

    agent: Mapped[Agent] = relationship(back_populates="favorites")
