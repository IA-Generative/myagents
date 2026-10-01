"""Téléchargement des fichiers générés par les agents, via un lien signé expirant.

Pas d'authentification Bearer : le lien est ouvert depuis le navigateur de l'utilisateur
d'Open WebUI, qui ne détient aucune clé. La signature HMAC fait office de capacité.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import signing
from app.db.session import get_db
from app.services import presentations as service

router = APIRouter(prefix="/presentations", tags=["presentations"])


@router.get("/{file_id}/download")
async def download_presentation(
    file_id: uuid.UUID,
    exp: int = Query(),
    sig: str = Query(max_length=128),
    db: AsyncSession = Depends(get_db),
):
    try:
        valid = signing.verify(file_id, exp, sig)
    except signing.SigningUnavailableError as exc:
        raise HTTPException(status_code=503, detail="signing_unavailable") from exc
    if not valid:
        raise HTTPException(status_code=403, detail="invalid_or_expired_link")

    generated = await service.get_file(db, file_id)
    if generated is None:
        raise HTTPException(status_code=404, detail="not_found")

    return Response(
        content=generated.data,
        media_type=generated.content_type,
        headers={
            "Content-Disposition": f'attachment; filename="{generated.filename}"',
            "Cache-Control": "private, no-store",
        },
    )
