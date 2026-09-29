"""Pydantic schemas for knowledge bases (RAG document collections)."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.knowledge import DocumentStatus


class KnowledgeBaseCreate(BaseModel):
    name: str


class KnowledgeBaseRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    creator_id: str
    name: str
    created_at: datetime


class KnowledgeDocumentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    knowledge_base_id: uuid.UUID
    filename: str
    char_count: int
    status: DocumentStatus
    created_at: datetime


class KnowledgeBaseDetail(KnowledgeBaseRead):
    documents: list[KnowledgeDocumentRead] = []
