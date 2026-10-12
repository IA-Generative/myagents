"""JSON-RPC 2.0 : formes et codes d'erreur standard."""

from __future__ import annotations

from typing import Any

PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603


class JsonRpcError(Exception):
    def __init__(self, code: int, message: str, data: Any = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.data = data


def reponse(id: Any, result: Any) -> dict:
    return {"jsonrpc": "2.0", "id": id, "result": result}


def erreur(id: Any, code: int, message: str, data: Any = None) -> dict:
    corps: dict = {
        "jsonrpc": "2.0",
        "id": id,
        "error": {"code": code, "message": message},
    }
    if data is not None:
        corps["error"]["data"] = data
    return corps


def valider_requete(message: Any) -> tuple[str, dict, Any, bool]:
    """(méthode, params, id, est_notification) ou JsonRpcError(INVALID_REQUEST)."""
    if not isinstance(message, dict) or message.get("jsonrpc") != "2.0":
        raise JsonRpcError(INVALID_REQUEST, "Invalid Request")
    method = message.get("method")
    if not isinstance(method, str) or not method:
        raise JsonRpcError(INVALID_REQUEST, "Invalid Request")
    params = message.get("params", {})
    if params is None:
        params = {}
    if not isinstance(params, dict):
        raise JsonRpcError(INVALID_PARAMS, "params must be an object")
    est_notification = "id" not in message or message.get("id") is None
    return method, params, message.get("id"), est_notification
