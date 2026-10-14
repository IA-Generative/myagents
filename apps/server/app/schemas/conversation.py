"""Pydantic schemas for conversation persistence and enriched chat responses."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.conversation import MessageRole


class ConversationCreate(BaseModel):
    agent_id: uuid.UUID
    title: str = Field(default="", max_length=500)


class ConversationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    agent_id: uuid.UUID
    title: str
    created_at: datetime
    updated_at: datetime
    last_message_at: datetime | None = None


class MessageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    role: MessageRole
    content: str
    tool_calls: dict | None = None
    tool_call_id: str | None = None
    metadata: dict | None = None
    created_at: datetime


class Citation(BaseModel):
    filename: str = ""
    document_id: str = ""
    chunk_id: str = ""
    score: float = 0.0
    snippet: str = ""


class ToolStep(BaseModel):
    tool_name: str
    args: dict = Field(default_factory=dict)
    result: str = ""
    status: str = "completed"


class ChatResponseEnriched(BaseModel):
    reply: str
    conversation_id: uuid.UUID | None = None
    message_id: uuid.UUID | None = None
    citations: list[Citation] = Field(default_factory=list)
    tool_steps: list[ToolStep] = Field(default_factory=list)
