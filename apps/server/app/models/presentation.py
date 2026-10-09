"""ORM model: GeneratedFile (fichiers produits par les tools d'agent, ex. présentations .pptx)."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, Integer, LargeBinary, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


def _utcnow() -> datetime:
    return datetime.now(UTC)


_TZ = DateTime(timezone=True)


class GeneratedFile(Base):
    __tablename__ = "generated_files"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    filename: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(255))
    data: Mapped[bytes] = mapped_column(LargeBinary)
    size: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(_TZ, default=_utcnow)
    expires_at: Mapped[datetime] = mapped_column(_TZ, index=True)
