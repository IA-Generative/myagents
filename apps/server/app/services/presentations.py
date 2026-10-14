"""Stockage temporaire des fichiers générés (en base : partagé entre réplicas, rootfs read-only)."""

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.presentation import GeneratedFile

PPTX_CONTENT_TYPE = (
    "application/vnd.openxmlformats-officedocument.presentationml.presentation"
)


async def purge_expired(db: AsyncSession) -> None:
    await db.execute(
        delete(GeneratedFile).where(GeneratedFile.expires_at < datetime.now(UTC))
    )


async def save_file(
    db: AsyncSession,
    *,
    filename: str,
    content_type: str,
    data: bytes,
    ttl: timedelta,
) -> GeneratedFile:
    # Purge opportuniste : évite un job de nettoyage dédié.
    await purge_expired(db)
    now = datetime.now(UTC)
    generated = GeneratedFile(
        filename=filename,
        content_type=content_type,
        data=data,
        size=len(data),
        created_at=now,
        expires_at=now + ttl,
    )
    db.add(generated)
    await db.commit()
    return generated


async def get_file(db: AsyncSession, file_id: uuid.UUID) -> GeneratedFile | None:
    return await db.get(GeneratedFile, file_id)
