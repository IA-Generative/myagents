"""Client OIDC côté serveur (flux code + PKCE) vers Keycloak : le navigateur ne voit aucun jeton."""

import base64
import hashlib
import hmac
import secrets
from dataclasses import dataclass
from urllib.parse import urlencode

import httpx
import jwt

from app.core import security
from app.core.config import get_settings
from app.core.security import AuthUser, OIDCError

_SCOPE = "openid profile email roles"
_OIDC_PATH = "protocol/openid-connect"


@dataclass(frozen=True)
class TokenSet:
    access_token: str
    refresh_token: str
    id_token: str
    expires_in: int
    refresh_expires_in: int


def redirect_uri() -> str:
    return f"{get_settings().web_public_url.rstrip('/')}/api/auth/callback"


def _public_realm() -> str:
    return get_settings().oidc_issuer.rstrip("/")


def _backchannel_realm() -> str:
    settings = get_settings()
    return (settings.oidc_internal_url or settings.oidc_issuer).rstrip("/")


def new_pkce() -> tuple[str, str]:
    """(code_verifier, code_challenge S256)."""
    verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(verifier.encode()).digest()
    return verifier, base64.urlsafe_b64encode(digest).rstrip(b"=").decode()


def authorization_url(state: str, nonce: str, challenge: str) -> str:
    params = {
        "response_type": "code",
        "client_id": get_settings().oidc_client_id,
        "redirect_uri": redirect_uri(),
        "scope": _SCOPE,
        "state": state,
        "nonce": nonce,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    }
    return f"{_public_realm()}/{_OIDC_PATH}/auth?{urlencode(params)}"


def logout_url(id_token: str) -> str:
    settings = get_settings()
    params = {
        "client_id": settings.oidc_client_id,
        "post_logout_redirect_uri": settings.web_public_url.rstrip("/") + "/",
    }
    if id_token:
        params["id_token_hint"] = id_token
    return f"{_public_realm()}/{_OIDC_PATH}/logout?{urlencode(params)}"


async def _token_request(data: dict[str, str]) -> TokenSet:
    settings = get_settings()
    auth = None
    if settings.oidc_client_secret:
        auth = (settings.oidc_client_id, settings.oidc_client_secret)
    else:
        data = {**data, "client_id": settings.oidc_client_id}
    # Adresse interne (réseau compose/cluster) : on ignore le proxy d'entreprise.
    async with httpx.AsyncClient(
        timeout=10, trust_env=not settings.oidc_internal_url
    ) as client:
        try:
            response = await client.post(
                f"{_backchannel_realm()}/{_OIDC_PATH}/token", data=data, auth=auth
            )
        except httpx.HTTPError as exc:
            raise OIDCError("issuer unavailable") from exc
    if response.status_code != 200:
        # `error` / `error_description` (RFC 6749 §5.2) ne contiennent pas de secret.
        try:
            err = response.json()
            detail = f"{err.get('error', '')}: {err.get('error_description', '')}"
        except ValueError:
            detail = ""
        raise OIDCError(
            f"token request rejected ({response.status_code}) {detail}".rstrip()
        )
    body = response.json()
    return TokenSet(
        access_token=body.get("access_token", ""),
        refresh_token=body.get("refresh_token", ""),
        id_token=body.get("id_token", ""),
        expires_in=int(body.get("expires_in", 60)),
        refresh_expires_in=int(body.get("refresh_expires_in", 0)),
    )


async def exchange_code(code: str, verifier: str) -> TokenSet:
    return await _token_request(
        {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri(),
            "code_verifier": verifier,
        }
    )


async def refresh(refresh_token: str) -> TokenSet:
    return await _token_request(
        {"grant_type": "refresh_token", "refresh_token": refresh_token}
    )


def user_from_tokens(tokens: TokenSet, nonce: str | None = None) -> AuthUser:
    """Valide les jetons (bloquant : JWKS) ; `nonce` n'est contrôlé qu'au retour du login."""
    try:
        access_claims = security._decode_token(tokens.access_token)
        if nonce is not None:
            id_claims = security._decode_token(
                tokens.id_token, audience=get_settings().oidc_client_id
            )
            if not hmac.compare_digest(str(id_claims.get("nonce", "")), nonce):
                raise OIDCError("nonce mismatch")
    except jwt.PyJWTError as exc:
        raise OIDCError(f"invalid token: {type(exc).__name__}: {exc}") from exc
    except httpx.HTTPError as exc:
        raise OIDCError("issuer unavailable") from exc
    return security._extract_user(access_claims)
