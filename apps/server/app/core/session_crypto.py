"""Chiffrement symétrique (Fernet) des jetons stockés en base et du cookie d'état du flux OIDC."""

import base64
import hashlib
import json
from typing import Any

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import get_settings


class SessionCryptoUnavailableError(RuntimeError):
    """Aucun secret configuré : on refuse de chiffrer plutôt que de stocker en clair."""


def _fernet() -> Fernet:
    settings = get_settings()
    secret = settings.session_secret or settings.oidc_client_secret
    if not secret:
        raise SessionCryptoUnavailableError(
            "SESSION_SECRET (ou OIDC_CLIENT_SECRET) n'est pas configuré"
        )
    key = hashlib.sha256(b"mes-agents.session.v1:" + secret.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(key))


def encrypt(value: str) -> str:
    return _fernet().encrypt(value.encode()).decode()


def decrypt(value: str) -> str | None:
    try:
        return _fernet().decrypt(value.encode()).decode()
    except InvalidToken:
        return None


def seal(data: dict[str, Any]) -> str:
    return encrypt(json.dumps(data))


def unseal(value: str, max_age: int) -> dict[str, Any] | None:
    """Déchiffre un cookie d'état ; None s'il est invalide, altéré ou trop ancien."""
    try:
        raw = _fernet().decrypt(value.encode(), ttl=max_age)
    except InvalidToken:
        return None
    return json.loads(raw)
