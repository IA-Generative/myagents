"""Liens de téléchargement signés (HMAC-SHA256) et expirants pour les fichiers générés."""

import hashlib
import hmac
import time
import uuid

from app.core.config import get_settings

_DOMAIN = b"mes-agents.presentation-link.v1"


class SigningUnavailableError(RuntimeError):
    """Aucun secret configuré : on refuse de produire ou de valider des liens."""


def _key() -> bytes:
    settings = get_settings()
    secret = settings.presentation_link_secret or settings.openwebui_api_key
    if not secret:
        raise SigningUnavailableError(
            "PRESENTATION_LINK_SECRET (ou OPENWEBUI_API_KEY) n'est pas configuré"
        )
    # Séparation de domaine : la clé Open WebUI ne sert jamais directement de clé HMAC.
    return hmac.new(secret.encode(), _DOMAIN, hashlib.sha256).digest()


def _signature(file_id: uuid.UUID, expires_at: int) -> str:
    message = f"{file_id}.{expires_at}".encode()
    return hmac.new(_key(), message, hashlib.sha256).hexdigest()


def build_download_url(file_id: uuid.UUID, ttl_seconds: int) -> str:
    expires_at = int(time.time()) + ttl_seconds
    base = get_settings().public_base_url.rstrip("/")
    sig = _signature(file_id, expires_at)
    return f"{base}/api/presentations/{file_id}/download?exp={expires_at}&sig={sig}"


def verify(file_id: uuid.UUID, expires_at: int, sig: str) -> bool:
    """Vérifie la signature (temps constant) puis l'expiration."""
    if not hmac.compare_digest(sig.encode(), _signature(file_id, expires_at).encode()):
        return False
    return expires_at >= time.time()
