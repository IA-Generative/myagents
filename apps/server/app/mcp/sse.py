"""Flux Server-Sent Events des notifications du serveur MCP (`GET /mcp`)."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator

from app.mcp import notifications


async def flux_notifications(
    sub: str, *, battement: float = 15.0
) -> AsyncIterator[str]:
    """Un commentaire d'ouverture, puis chaque notification en événement `message` ; un battement
    (`: ping`) toutes les `battement` secondes pour garder la connexion."""
    file = notifications.diffuseur.abonner(sub)
    try:
        yield ": mes-agents connecté\n\n"
        while True:
            try:
                message = await asyncio.wait_for(file.get(), timeout=battement)
            except TimeoutError:
                yield ": ping\n\n"
                continue
            yield f"event: message\ndata: {json.dumps(message, ensure_ascii=False)}\n\n"
    finally:
        notifications.diffuseur.desabonner(sub, file)
