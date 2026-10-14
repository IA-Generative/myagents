"""ORM models: Conversation, ChatMessage (persisted multi-turn conversations)."""

import enum
import uuid
from datetime import UTC, datetime

from sqlalchemy import JSON, DateTime, Enum, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


def _utcnow() -> datetime:
    return datetime.now(UTC)


_TZ = DateTime(timezone=True)


class MessageRole(str, enum.Enum):
    user = "user"
    assistant = "assistant"
    tool = "tool"
    system = "system"


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    agent_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("agents.id"), index=True)
    user_id: Mapped[str] = mapped_column(String(255), index=True)
    title: Mapped[str] = mapped_column(String(500), default="")
    created_at: Mapped[datetime] = mapped_column(_TZ, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(_TZ, default=_utcnow, onupdate=_utcnow)
    last_message_at: Mapped[datetime | None] = mapped_column(_TZ, nullable=True)

    messages: Mapped[list[ChatMessageRecord]] = relationship(
        back_populates="conversation",
        order_by="asc(ChatMessageRecord.created_at)",
        cascade="all, delete-orphan",
    )


class ChatMessageRecord(Base):
    __tablename__ = "chat_messages"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("conversations.id"), index=True
    )
    role: Mapped[MessageRole] = mapped_column(
        Enum(MessageRole, native_enum=False, length=20, create_constraint=False),
        default=MessageRole.user,
    )
    content: Mapped[str] = mapped_column(Text)
    tool_calls: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    tool_call_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSON, nullable=True)
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("chat_messages.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(_TZ, default=_utcnow)

    conversation: Mapped[Conversation] = relationship(back_populates="messages")
