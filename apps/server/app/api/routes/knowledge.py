"""Routes: create/list/delete knowledge bases, upload documents for RAG ingestion."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user_id
from app.db.session import get_db
from app.llm.client import LlmUnavailableError
from app.schemas.knowledge import (
    KnowledgeBaseCreate,
    KnowledgeBaseDetail,
    KnowledgeDocumentRead,
)
from app.services import knowledge as knowledge_service

router = APIRouter(prefix="/knowledge", tags=["knowledge"])

_ALLOWED_EXTENSIONS = (".txt", ".md")


async def _get_owned_kb(db: AsyncSession, kb_id: uuid.UUID, user_id: str):
    kb = await knowledge_service.get_knowledge_base(db, kb_id)
    if kb is None:
        raise HTTPException(status_code=404, detail="not_found")
    if kb.creator_id != user_id:
        raise HTTPException(status_code=403, detail="forbidden")
    return kb


@router.get("", response_model=list[KnowledgeBaseDetail])
async def list_knowledge_bases(
    db: AsyncSession = Depends(get_db), user_id: str = Depends(get_current_user_id)
):
    return await knowledge_service.list_my_knowledge_bases(db, user_id)


@router.post("", response_model=KnowledgeBaseDetail)
async def create_knowledge_base(
    payload: KnowledgeBaseCreate,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    return await knowledge_service.create_knowledge_base(db, user_id, payload)


@router.get("/{kb_id}", response_model=KnowledgeBaseDetail)
async def get_knowledge_base(
    kb_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    return await _get_owned_kb(db, kb_id, user_id)


@router.delete("/{kb_id}")
async def delete_knowledge_base(
    kb_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    kb = await _get_owned_kb(db, kb_id, user_id)
    await knowledge_service.delete_knowledge_base(db, kb)
    return {"id": str(kb_id)}


@router.post("/{kb_id}/documents", response_model=KnowledgeDocumentRead)
async def upload_document(
    kb_id: uuid.UUID,
    file: UploadFile,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    kb = await _get_owned_kb(db, kb_id, user_id)
    filename = file.filename or "document.txt"
    if not filename.lower().endswith(_ALLOWED_EXTENSIONS):
        raise HTTPException(status_code=422, detail="unsupported_file_type")

    raw = await file.read()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise HTTPException(status_code=422, detail="invalid_encoding") from exc
    if not text.strip():
        raise HTTPException(status_code=422, detail="empty_document")

    try:
        return await knowledge_service.add_document(db, kb, filename, text)
    except LlmUnavailableError as exc:
        raise HTTPException(status_code=502, detail="embedding_unavailable") from exc
