"""Sessions serveur du flux OIDC : jetons Keycloak en base (chiffrés), cookie opaque côté navigateur."""

import asyncio
import hashlib
import logging
import secrets
from dataclasses import asdict
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import oidc_client
from app.core.config import get_settings
from app.core.oidc_client import TokenSet
from app.core.security import AuthUser, OIDCError
from app.core.session_crypto import decrypt, encrypt
from app.models.auth_session import AuthSession

logger = logging.getLogger(__name__)

SESSION_COOKIE = "myagents_session"
# Marge pour renouveler le jeton d'accès avant son expiration.
_REFRESH_SKEW = timedelta(seconds=30)


def _hash(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def _aware(value: datetime) -> datetime:
    # SQLite restitue des datetimes naïfs.
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def _enc(value: str) -> str:
    return encrypt(value) if value else ""


async def purge_expired(db: AsyncSession) -> None:
    await db.execute(
        delete(AuthSession).where(AuthSession.expires_at < datetime.now(UTC))
    )


async def create_session(db: AsyncSession, user: AuthUser, tokens: TokenSet) -> str:
    """Crée la session et renvoie la valeur du cookie (jamais stockée en clair)."""
    await purge_expired(db)
    now = datetime.now(UTC)
    expires_at = now + timedelta(hours=get_settings().session_ttl_hours)
    if tokens.refresh_expires_in > 0:
        expires_at = min(expires_at, now + timedelta(seconds=tokens.refresh_expires_in))

    raw = secrets.token_urlsafe(32)
    db.add(
        AuthSession(
            token_hash=_hash(raw),
            user=asdict(user),
            refresh_token_enc=_enc(tokens.refresh_token),
            id_token_enc=_enc(tokens.id_token),
            access_expires_at=now + timedelta(seconds=tokens.expires_in),
            expires_at=expires_at,
        )
    )
    await db.commit()
    return raw


async def _find(db: AsyncSession, raw: str) -> AuthSession | None:
    result = await db.execute(
        select(AuthSession).where(AuthSession.token_hash == _hash(raw))
    )
    return result.scalar_one_or_none()


async def _find_for_update(db: AsyncSession, raw: str) -> AuthSession | None:
    """Trouve la session avec verrou FOR UPDATE SKIP LOCKED (PostgreSQL ; SQLite ignore)."""
    try:
        result = await db.execute(
            select(AuthSession)
            .where(AuthSession.token_hash == _hash(raw))
            .with_for_update(skip_locked=True, read=False)
        )
        return result.scalar_one_or_none()
    except Exception:
        # SQLite ne supporte pas FOR UPDATE SKIP LOCKED ; on retombe sur une lecture simple.
        return await _find(db, raw)


async def _drop(db: AsyncSession, session: AuthSession) -> None:
    await db.delete(session)
    await db.commit()


async def resolve_session(db: AsyncSession, raw: str) -> AuthUser | None:
    """Utilisateur de la session, jeton d'accès renouvelé si besoin ; None si invalide."""
    session = await _find(db, raw)
    if session is None:
        return None
    now = datetime.now(UTC)
    if _aware(session.expires_at) <= now:
        await _drop(db, session)
        return None

    if _aware(session.access_expires_at) - _REFRESH_SKEW > now:
        return AuthUser(**session.user)

    # Access token expiré ou expirant : tenter de verrouiller pour le refresh
    session = await _find_for_update(db, raw)
    if session is None:
        # Un concurrent a verrouillé (SKIP LOCKED) ou supprimé la session.
        # Relire sans verrou : peut-être que le concurrent a déjà rafraîchi.
        session = await _find(db, raw)
        if session is None:
            return None
        # Si le concurrent a rafraîchi entre-temps, l'access token est valide.
        if _aware(session.access_expires_at) - _REFRESH_SKEW > now:
            return AuthUser(**session.user)
        return None  # Toujours expiré, on refuse proprement

    refresh_token = (
        decrypt(session.refresh_token_enc) if session.refresh_token_enc else None
    )
    if not refresh_token:
        await _drop(db, session)
        return None
    try:
        tokens = await oidc_client.refresh(refresh_token)
        user = await asyncio.to_thread(oidc_client.user_from_tokens, tokens)
    except OIDCError as exc:
        logger.warning("renouvellement de session refusé: %s", exc)
        # Keycloak injoignable : on garde la session, seul un refus l'invalide.
        if "unavailable" not in str(exc):
            await _drop(db, session)
        return None
    session.user = asdict(user)
    session.refresh_token_enc = (
        _enc(tokens.refresh_token) or session.refresh_token_enc
    )
    session.id_token_enc = _enc(tokens.id_token) or session.id_token_enc
    session.access_expires_at = now + timedelta(seconds=tokens.expires_in)
    await db.commit()

    return AuthUser(**session.user)


async def end_session(db: AsyncSession, raw: str) -> str:
    """Supprime la session ; renvoie l'id_token (pour id_token_hint) ou ''."""
    session = await _find(db, raw)
    if session is None:
        return ""
    id_token = decrypt(session.id_token_enc) if session.id_token_enc else None
    await _drop(db, session)
    return id_token or ""
