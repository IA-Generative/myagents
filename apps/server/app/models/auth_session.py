"""ORM model: AuthSession (session serveur du flux OIDC ; le navigateur ne détient qu'un cookie opaque)."""

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


def _utcnow() -> datetime:
    return datetime.now(UTC)


_TZ = DateTime(timezone=True)


class AuthSession(Base):
    __tablename__ = "auth_sessions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    # SHA-256 du cookie : une fuite de la base ne permet pas de rejouer une session.
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    user: Mapped[dict[str, Any]] = mapped_column(JSON)
    # Jetons Keycloak chiffrés (voir core/session_crypto.py).
    refresh_token_enc: Mapped[str] = mapped_column(Text, default="")
    id_token_enc: Mapped[str] = mapped_column(Text, default="")
    access_expires_at: Mapped[datetime] = mapped_column(_TZ)
    expires_at: Mapped[datetime] = mapped_column(_TZ, index=True)
    created_at: Mapped[datetime] = mapped_column(_TZ, default=_utcnow)
