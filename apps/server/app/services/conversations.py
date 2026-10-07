"""Business logic for conversation and message persistence."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.conversation import ChatMessageRecord, Conversation, MessageRole
from app.schemas.conversation import ConversationRead, MessageRead


async def create_conversation(
    db: AsyncSession, agent_id: uuid.UUID, user_id: str, title: str = ""
) -> Conversation:
    conv = Conversation(agent_id=agent_id, user_id=user_id, title=title)
    db.add(conv)
    await db.commit()
    await db.refresh(conv)
    return conv


async def get_conversation(
    db: AsyncSession, conv_id: uuid.UUID, user_id: str
) -> Conversation | None:
    stmt = (
        select(Conversation)
        .options(selectinload(Conversation.messages))
        .where(Conversation.id == conv_id, Conversation.user_id == user_id)
    )
    return (await db.execute(stmt)).scalar_one_or_none()


async def list_conversations(
    db: AsyncSession, user_id: str, agent_id: uuid.UUID | None = None
) -> list[Conversation]:
    stmt = select(Conversation).where(Conversation.user_id == user_id)
    if agent_id is not None:
        stmt = stmt.where(Conversation.agent_id == agent_id)
    stmt = stmt.order_by(Conversation.updated_at.desc())
    return list((await db.execute(stmt)).scalars().all())


async def delete_conversation(db: AsyncSession, conv: Conversation) -> None:
    await db.delete(conv)
    await db.commit()


async def add_message(
    db: AsyncSession,
    conv_id: uuid.UUID,
    role: MessageRole,
    content: str,
    *,
    tool_calls: dict | None = None,
    tool_call_id: str | None = None,
    metadata: dict | None = None,
    parent_id: uuid.UUID | None = None,
) -> ChatMessageRecord:
    msg = ChatMessageRecord(
        conversation_id=conv_id,
        role=role,
        content=content,
        tool_calls=tool_calls,
        tool_call_id=tool_call_id,
        metadata_=metadata,
        parent_id=parent_id,
    )
    db.add(msg)
    conv = await db.get(Conversation, conv_id)
    if conv is not None:
        conv.last_message_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(msg)
    return msg


def to_conversation_read(conv: Conversation) -> ConversationRead:
    return ConversationRead.model_validate(conv)


def to_message_read(msg: ChatMessageRecord) -> MessageRead:
    return MessageRead.model_validate(msg)


async def get_messages(db: AsyncSession, conv_id: uuid.UUID) -> list[ChatMessageRecord]:
    stmt = (
        select(ChatMessageRecord)
        .where(ChatMessageRecord.conversation_id == conv_id)
        .order_by(ChatMessageRecord.created_at)
    )
    return list((await db.execute(stmt)).scalars().all())
