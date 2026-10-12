"""Transport Streamable HTTP du serveur MCP : `POST /mcp` (requêtes et notifications JSON-RPC),
`GET /mcp` (flux SSE des notifications du serveur), `DELETE /mcp` (fin de session)."""

from __future__ import annotations

import json
import logging
import uuid

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps_v2 import exiger_portee
from app.core.portees import Operation
from app.core.security import AuthUser
from app.db.session import get_db
from app.mcp import jsonrpc, server
from app.mcp.sse import flux_notifications
from app.services.execution import ContexteAppel

router = APIRouter(tags=["mcp"])
logger = logging.getLogger(__name__)

_lecteur = exiger_portee(Operation.LISTER)


async def _traiter_un(db, user, ctx, message) -> dict | None:
    try:
        method, params, rid, notification = jsonrpc.valider_requete(message)
    except jsonrpc.JsonRpcError as exc:
        return jsonrpc.erreur(
            message.get("id") if isinstance(message, dict) else None,
            exc.code,
            exc.message,
        )
    if notification:
        if method not in server.NOTIFICATIONS_ADMISES:
            logger.debug("[mcp] notification ignorée : %s", method)
        return None
    try:
        resultat = await server.traiter(db, user, ctx, method, params)
    except jsonrpc.JsonRpcError as exc:
        return jsonrpc.erreur(rid, exc.code, exc.message, exc.data)
    except Exception as exc:
        logger.exception("[mcp] erreur interne sur %s", method)
        return jsonrpc.erreur(
            rid, jsonrpc.INTERNAL_ERROR, f"Internal error: {type(exc).__name__}"
        )
    return jsonrpc.reponse(rid, resultat)


@router.post("/mcp", summary="Requêtes JSON-RPC du protocole MCP (Streamable HTTP)")
async def mcp_post(
    request: Request,
    user: AuthUser = Depends(_lecteur),
    db: AsyncSession = Depends(get_db),
):
    """`initialize`, `ping`, `tools/list`, `tools/call`, `prompts/list`, `prompts/get` ; lots admis."""
    brut = await request.body()
    try:
        corps = json.loads(brut or b"")
    except ValueError:
        return JSONResponse(
            status_code=400,
            content=jsonrpc.erreur(None, jsonrpc.PARSE_ERROR, "Parse error"),
        )
    session = request.headers.get("mcp-session-id") or uuid.uuid4().hex
    ctx = ContexteAppel(
        user=user, jeton=getattr(request.state, "jeton", None), route="mcp"
    )
    messages = corps if isinstance(corps, list) else [corps]
    if isinstance(corps, list) and not corps:
        return JSONResponse(
            status_code=400,
            content=jsonrpc.erreur(None, jsonrpc.INVALID_REQUEST, "Invalid Request"),
        )
    reponses = [
        r
        for r in [await _traiter_un(db, user, ctx, m) for m in messages]
        if r is not None
    ]
    entetes = {"Mcp-Session-Id": session}
    if not reponses:
        return Response(status_code=202, headers=entetes)
    contenu = reponses if isinstance(corps, list) else reponses[0]
    return JSONResponse(status_code=200, content=contenu, headers=entetes)


@router.get("/mcp", summary="Flux des notifications du serveur (SSE)")
async def mcp_get(request: Request, user: AuthUser = Depends(_lecteur)):
    """`notifications/tools/list_changed` quand le catalogue visible de la personne change."""
    accepte = request.headers.get("accept", "")
    if "text/event-stream" not in accepte:
        return JSONResponse(
            status_code=405,
            content={
                "error": {
                    "code": "invalid_request",
                    "message": "GET /mcp exige Accept: text/event-stream",
                }
            },
            headers={"Allow": "POST, DELETE"},
        )
    return StreamingResponse(
        flux_notifications(user.user_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-store",
            "X-Accel-Buffering": "no",
            "Mcp-Session-Id": request.headers.get("mcp-session-id") or uuid.uuid4().hex,
        },
    )


@router.delete("/mcp", status_code=204, summary="Fin de session MCP")
async def mcp_delete(user: AuthUser = Depends(_lecteur)):
    """Serveur sans état : la fin de session est acceptée sans effet."""
    return Response(status_code=204)
