"""Faux serveur MCP de dépendance (Streamable HTTP, JSON-RPC 2.0) pour le compose de conformité.

Un outil `rechercher` qui RENVOIE l'identité reçue (azp, sub lus dans le jeton, sans le vérifier :
c'est une doublure) et les arguments : preuve que Mes agents relaie l'identité de la personne.
Doublure de Légifrance pour le chantier 3 (`legifrance_search`).
"""

import base64
import json
import uuid

from fastapi import FastAPI, Request, Response

app = FastAPI(title="faux-mcp-dependance")

OUTILS = [
    {
        "name": "rechercher",
        "title": "Rechercher (doublure)",
        "description": "Renvoie l'identité reçue et les arguments.",
        "inputSchema": {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
        "annotations": {
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    },
    {
        "name": "reserver",
        "title": "Réserver (doublure)",
        "description": "Réserve un créneau et rend un numéro.",
        "inputSchema": {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
        "annotations": {
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": False,
            "openWorldHint": True,
        },
    },
    {
        "name": "legifrance_search",
        "title": "Légifrance (doublure)",
        "description": "Trois résultats figés.",
        "inputSchema": {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
        "annotations": {
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    },
]


def _claims(autorisation: str) -> dict:
    try:
        jeton = autorisation.split(" ", 1)[1]
        partie = jeton.split(".")[1]
        return json.loads(base64.urlsafe_b64decode(partie + "=" * (-len(partie) % 4)))
    except Exception:  # noqa: BLE001 — doublure
        return {}


@app.post("/mcp")
async def mcp(request: Request):
    corps = await request.json()
    method = corps.get("method")
    rid = corps.get("id")
    if method == "initialize":
        return Response(
            json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": rid,
                    "result": {
                        "protocolVersion": corps.get("params", {}).get(
                            "protocolVersion", "2025-06-18"
                        ),
                        "capabilities": {"tools": {}},
                        "serverInfo": {"name": "faux-mcp", "version": "1"},
                    },
                }
            ),
            media_type="application/json",
            headers={"Mcp-Session-Id": uuid.uuid4().hex},
        )
    if method and method.startswith("notifications/"):
        return Response(status_code=202)
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": rid, "result": {"tools": OUTILS}}
    if method == "tools/call":
        params = corps.get("params", {})
        claims = _claims(request.headers.get("authorization", ""))
        if params.get("name") == "legifrance_search":
            texte = json.dumps(
                {
                    "results": [
                        {
                            "title": f"Article {i} — {params.get('arguments', {}).get('query', '')}",
                            "id": f"LEGIARTI{i:012d}",
                            "url": f"https://www.legifrance.gouv.fr/doublure/{i}",
                        }
                        for i in range(1, 4)
                    ]
                },
                ensure_ascii=False,
            )
        else:
            texte = json.dumps(
                {
                    "azp": claims.get("azp"),
                    "sub": claims.get("sub"),
                    "aud": claims.get("aud"),
                    "arguments": params.get("arguments", {}),
                },
                ensure_ascii=False,
            )
        return {
            "jsonrpc": "2.0",
            "id": rid,
            "result": {"content": [{"type": "text", "text": texte}], "isError": False},
        }
    if method == "ping":
        return {"jsonrpc": "2.0", "id": rid, "result": {}}
    return {
        "jsonrpc": "2.0",
        "id": rid,
        "error": {"code": -32601, "message": "Method not found"},
    }


@app.delete("/mcp")
async def fin():
    return Response(status_code=204)


@app.get("/health")
async def health():
    return {"status": "ok"}
