"""Authentification de la SPA : flux OIDC code + PKCE mené par le server (BFF).

Le navigateur ne manipule jamais de jeton Keycloak : il reçoit un cookie de session opaque
(HttpOnly, SameSite=Lax) ; les jetons restent chiffrés en base.
"""

import asyncio
import hmac
import logging
import secrets

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import check_csrf, get_current_user
from app.core import oidc_client
from app.core.config import get_settings
from app.core.security import AuthUser, OIDCError, has_required_group
from app.core.session_crypto import SessionCryptoUnavailableError, seal, unseal
from app.db.session import get_db
from app.services import auth_sessions

router = APIRouter(prefix="/auth", tags=["auth"])
# Routes hors /api : liens de navigation (pas d'appel XHR), comme la déconnexion du menu commun.
racine = APIRouter(tags=["auth"])
logger = logging.getLogger(__name__)

_FLOW_COOKIE = "myagents_oidc_flow"
_FLOW_TTL_SECONDS = 600
_FLOW_COOKIE_PATH = "/api/auth"


class AuthMe(BaseModel):
    id: str
    username: str
    email: str
    roles: list[str]
    groups: list[str]
    is_admin: bool
    # Sans SSO (dev), l'identité est un substitut : le front masque alors la déconnexion.
    sso_enabled: bool


def _safe_return_to(value: str | None) -> str:
    """Chemin relatif uniquement : évite la redirection ouverte après connexion."""
    if (
        not value
        or not value.startswith("/")
        or value.startswith("//")
        or "\\" in value
        or any(ord(ch) < 32 for ch in value)
    ):
        return "/"
    return value


@router.get("/login")
async def login(return_to: str | None = None):
    settings = get_settings()
    target = _safe_return_to(return_to)
    if not settings.oidc_enabled:
        return RedirectResponse(target, status_code=302)

    verifier, challenge = oidc_client.new_pkce()
    state, nonce = secrets.token_urlsafe(24), secrets.token_urlsafe(24)
    try:
        flow = seal(
            {"state": state, "nonce": nonce, "verifier": verifier, "return_to": target}
        )
    except SessionCryptoUnavailableError as exc:
        raise HTTPException(status_code=503, detail="session_unavailable") from exc

    response = RedirectResponse(
        oidc_client.authorization_url(state, nonce, challenge), status_code=302
    )
    response.set_cookie(
        _FLOW_COOKIE,
        flow,
        max_age=_FLOW_TTL_SECONDS,
        httponly=True,
        samesite="lax",
        secure=settings.cookie_secure,
        path=_FLOW_COOKIE_PATH,
    )
    return response


def _acces_refuse() -> HTMLResponse:
    response = HTMLResponse(
        '<!doctype html><html lang="fr"><meta charset="utf-8">'
        "<title>Accès réservé</title>"
        "<p>Mes agents est réservé, pendant la bêta, aux membres d'un groupe d'utilisateurs."
        " Votre compte n'en fait pas partie.</p></html>",
        status_code=403,
    )
    response.delete_cookie(_FLOW_COOKIE, path=_FLOW_COOKIE_PATH)
    return response


@router.get("/callback")
async def callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    settings = get_settings()
    cookie = request.cookies.get(_FLOW_COOKIE)
    try:
        flow = unseal(cookie, _FLOW_TTL_SECONDS) if cookie else None
    except SessionCryptoUnavailableError as exc:
        raise HTTPException(status_code=503, detail="session_unavailable") from exc
    if flow is None or not state or not hmac.compare_digest(flow["state"], state):
        raise HTTPException(status_code=400, detail="invalid_state")
    if error or not code:
        raise HTTPException(status_code=400, detail="authorization_failed")

    try:
        tokens = await oidc_client.exchange_code(code, flow["verifier"])
        user = await asyncio.to_thread(
            oidc_client.user_from_tokens, tokens, flow["nonce"]
        )
        if not has_required_group(user):
            # Aucune session créée. On trace le motif sans nommer la personne.
            logger.warning(
                "accès refusé : groupe exigé absent du jeton (%d groupe(s) présenté(s))",
                len(user.groups),
            )
            return _acces_refuse()
        raw = await auth_sessions.create_session(db, user, tokens)
    except OIDCError as exc:
        logger.warning("callback OIDC refusé: %s", exc)
        error_code = "auth_unavailable" if "unavailable" in str(exc) else "authentication_failed"
        response = RedirectResponse("/?auth_error=" + error_code, status_code=302)
        response.delete_cookie(_FLOW_COOKIE, path=_FLOW_COOKIE_PATH)
        return response
    except SessionCryptoUnavailableError as exc:
        logger.warning("callback session crypto unavailable: %s", exc)
        response = RedirectResponse("/?auth_error=session_unavailable", status_code=302)
        response.delete_cookie(_FLOW_COOKIE, path=_FLOW_COOKIE_PATH)
        return response

    response = RedirectResponse(_safe_return_to(flow["return_to"]), status_code=302)
    response.set_cookie(
        auth_sessions.SESSION_COOKIE,
        raw,
        max_age=settings.session_ttl_hours * 3600,
        httponly=True,
        samesite="lax",
        secure=settings.cookie_secure,
        path="/",
    )
    response.delete_cookie(_FLOW_COOKIE, path=_FLOW_COOKIE_PATH)
    return response


@router.get("/me", response_model=AuthMe)
async def me(user: AuthUser = Depends(get_current_user)):
    return AuthMe(
        id=user.user_id,
        username=user.username,
        email=user.email,
        roles=user.roles,
        groups=user.groups,
        is_admin=user.is_admin,
        sso_enabled=get_settings().oidc_enabled,
    )


@router.post("/logout")
async def logout(request: Request, db: AsyncSession = Depends(get_db)):
    raw = request.cookies.get(auth_sessions.SESSION_COOKIE)
    # Rien à protéger sans session : pas de contrôle CSRF (dev sans SSO, cookie déjà expiré).
    if raw:
        check_csrf(request)
    id_token = await auth_sessions.end_session(db, raw) if raw else ""
    url = oidc_client.logout_url(id_token) if get_settings().oidc_enabled else "/"
    response = JSONResponse({"logout_url": url})
    response.delete_cookie(auth_sessions.SESSION_COOKIE, path="/")
    return response


@racine.get("/deconnexion")
async def deconnexion(request: Request, db: AsyncSession = Depends(get_db)):
    """Déconnexion par simple lien : celle du menu commun de la bêta (`sortie` de sa table APPS).

    Supprime la session puis renvoie vers la déconnexion Keycloak, qui revient à l'accueil.
    Sans contrôle CSRF : un lien ne porte pas d'en-tête, et le pire qu'un tiers obtienne est
    de déconnecter quelqu'un — même compromis que la route /deconnexion de l'ancienne app.
    """
    raw = request.cookies.get(auth_sessions.SESSION_COOKIE)
    id_token = await auth_sessions.end_session(db, raw) if raw else ""
    url = oidc_client.logout_url(id_token) if get_settings().oidc_enabled else "/"
    response = RedirectResponse(url, status_code=302)
    response.delete_cookie(auth_sessions.SESSION_COOKIE, path="/")
    return response
