"""ORM model: GuardEvent (journal d'audit de la garde anti-prompt-injection)."""

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


def _utcnow() -> datetime:
    return datetime.now(UTC)


class GuardEvent(Base):
    """Équivalent de `ab_guard_events` en production : heure, utilisateur, signaux.

    Le contenu inspecté n'est jamais stocké, seulement les signaux déclenchés.
    """

    __tablename__ = "guard_events"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, index=True
    )
    # Chaîne libre : un log d'audit ne doit jamais échouer sur un identifiant inattendu.
    user_id: Mapped[str | None] = mapped_column(String(255), index=True)
    route: Mapped[str] = mapped_column(String(100))
    stage: Mapped[str] = mapped_column(String(20))
    role: Mapped[str | None] = mapped_column(String(20))
    severity: Mapped[str] = mapped_column(String(20))
    signals: Mapped[list[dict[str, Any]]] = mapped_column(JSON)
