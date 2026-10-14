"""ORM models: KnowledgeBase, KnowledgeDocument (RAG sources attachable to agents)."""

import enum
import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


def _utcnow() -> datetime:
    return datetime.now(UTC)


_TZ = DateTime(timezone=True)


class DocumentStatus(str, enum.Enum):
    pending = "pending"
    indexed = "indexed"
    failed = "failed"


class KnowledgeBase(Base):
    __tablename__ = "knowledge_bases"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    creator_id: Mapped[str] = mapped_column(String(255), index=True)
    name: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(_TZ, default=_utcnow)

    documents: Mapped[list[KnowledgeDocument]] = relationship(
        back_populates="knowledge_base", cascade="all, delete-orphan"
    )


class KnowledgeDocument(Base):
    __tablename__ = "knowledge_documents"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    knowledge_base_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("knowledge_bases.id")
    )
    filename: Mapped[str] = mapped_column(String(255))
    char_count: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[DocumentStatus] = mapped_column(default=DocumentStatus.pending)
    created_at: Mapped[datetime] = mapped_column(_TZ, default=_utcnow)

    knowledge_base: Mapped[KnowledgeBase] = relationship(back_populates="documents")
