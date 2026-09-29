"""Business logic for knowledge base CRUD and document ingestion."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.llm import rag
from app.llm.client import LlmUnavailableError
from app.models.knowledge import DocumentStatus, KnowledgeBase, KnowledgeDocument
from app.schemas.knowledge import KnowledgeBaseCreate


def _with_documents(stmt):
    return stmt.options(selectinload(KnowledgeBase.documents))


async def create_knowledge_base(
    db: AsyncSession, creator_id: str, payload: KnowledgeBaseCreate
) -> KnowledgeBase:
    kb = KnowledgeBase(creator_id=creator_id, name=payload.name)
    db.add(kb)
    await db.commit()
    await db.refresh(kb, attribute_names=["documents"])
    return kb


async def get_knowledge_base(
    db: AsyncSession, kb_id: uuid.UUID
) -> KnowledgeBase | None:
    stmt = _with_documents(select(KnowledgeBase).where(KnowledgeBase.id == kb_id))
    return (await db.execute(stmt)).scalar_one_or_none()


async def list_my_knowledge_bases(
    db: AsyncSession, creator_id: str
) -> list[KnowledgeBase]:
    stmt = _with_documents(
        select(KnowledgeBase)
        .where(KnowledgeBase.creator_id == creator_id)
        .order_by(KnowledgeBase.created_at.desc())
    )
    return list((await db.execute(stmt)).scalars().all())


async def delete_knowledge_base(db: AsyncSession, kb: KnowledgeBase) -> None:
    rag.delete_knowledge_base(str(kb.id))
    await db.delete(kb)
    await db.commit()


async def add_document(
    db: AsyncSession, kb: KnowledgeBase, filename: str, text: str
) -> KnowledgeDocument:
    document = KnowledgeDocument(
        knowledge_base_id=kb.id,
        filename=filename,
        char_count=len(text),
        status=DocumentStatus.pending,
    )
    db.add(document)
    await db.commit()
    await db.refresh(document)

    try:
        rag.ingest_text(str(kb.id), filename, text)
    except Exception as exc:  # embedding/vector-store endpoint unreachable or erroring
        document.status = DocumentStatus.failed
        await db.commit()
        await db.refresh(document)
        raise LlmUnavailableError(str(exc)) from exc

    document.status = DocumentStatus.indexed
    await db.commit()
    await db.refresh(document)
    return document
