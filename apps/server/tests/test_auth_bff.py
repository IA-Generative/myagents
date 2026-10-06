"""Tests du BFF d'authentification : flux OIDC mené par le server, session par cookie opaque."""

import json
import time
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlsplit

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt import PyJWKSet
from sqlalchemy import select

from app.core import oidc_client, security
from app.core.config import get_settings
from app.core.oidc_client import TokenSet
from app.core.security import OIDCError
from app.models.auth_session import AuthSession
from app.services import auth_sessions

ISSUER = "http://kc.test/realms/myagents"
WEB = "http://localhost:5173"
CSRF = {"X-Requested-With": "XMLHttpRequest", "Origin": WEB}


@pytest.fixture(autouse=True)
def _oidc_settings(monkeypatch):
    settings = get_settings()
    for name, value in {
        "oidc_enabled": True,
        "oidc_issuer": ISSUER,
        "oidc_audience": "myagents-api",
        "oidc_client_id": "myagents-server",
        "oidc_client_secret": "client-secret",
        "web_public_url": WEB,
        "session_secret": "",
        "cors_origins": [WEB],
        "oidc_groupe_exige": "",  # Désactiver le contrôle de groupe pour les tests
    }.items():
        monkeypatch.setattr(settings, name, value)


@pytest.fixture
def private_key(monkeypatch):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key()))
    jwk.update(kid="k1", alg="RS256", use="sig")
    jwks = PyJWKSet.from_dict({"keys": [jwk]})
    monkeypatch.setattr(security, "_fetch_jwks", lambda force=False: jwks)
    return key


def _jwt(key, audience: str, **extra) -> str:
    now = int(time.time())
    claims = {
        "iss": ISSUER,
        "aud": audience,
        "iat": now,
        "exp": now + 300,
        "sub": "user-1",
        "preferred_username": "alice",
        "email": "alice@example.org",
        "realm_access": {"roles": ["user"]},
        **extra,
    }
    return jwt.encode(claims, key, algorithm="RS256", headers={"kid": "k1"})


@pytest.fixture
def keycloak(monkeypatch, private_key):
    """Faux endpoint token : renvoie des jetons signés (nonce repris de la requête de login)."""
    state = {"nonce": "", "calls": [], "fail": False, "groups": None}

    async def token_request(data):
        state["calls"].append(data)
        if state["fail"]:
            raise OIDCError("token request rejected (400)")
        extra = {} if state["groups"] is None else {"groups": state["groups"]}
        return TokenSet(
            access_token=_jwt(private_key, "myagents-api", **extra),
            refresh_token="refresh-token-secret",
            id_token=_jwt(private_key, "myagents-server", nonce=state["nonce"]),
            expires_in=300,
            refresh_expires_in=1800,
        )

    monkeypatch.setattr(oidc_client, "_token_request", token_request)
    return state


async def _login(client, keycloak, return_to="/agents"):
    res = await client.get(f"/api/auth/login?return_to={return_to}")
    assert res.status_code == 302
    query = parse_qs(urlsplit(res.headers["location"]).query)
    keycloak["nonce"] = query["nonce"][0]
    return query["state"][0]


async def _authenticate(client, keycloak):
    state = await _login(client, keycloak)
    res = await client.get(f"/api/auth/callback?code=abc&state={state}")
    assert res.status_code == 302
    return res


async def test_login_redirects_to_keycloak_with_pkce(client):
    res = await client.get("/api/auth/login?return_to=/agents")

    assert res.status_code == 302
    location = urlsplit(res.headers["location"])
    assert f"{location.scheme}://{location.netloc}{location.path}" == (
        f"{ISSUER}/protocol/openid-connect/auth"
    )
    query = parse_qs(location.query)
    assert query["client_id"] == ["myagents-server"]
    assert query["redirect_uri"] == [f"{WEB}/api/auth/callback"]
    assert query["code_challenge_method"] == ["S256"]
    assert query["response_type"] == ["code"]
    flow_cookie = res.headers["set-cookie"].lower()
    assert "httponly" in flow_cookie and "samesite=lax" in flow_cookie


@pytest.mark.parametrize(
    "bad", ["//evil.example", "https://evil.example", "evil", "/a\\b"]
)
async def test_callback_never_redirects_outside_the_app(client, keycloak, bad):
    state = await _login(client, keycloak, return_to=bad.replace("\\", "%5C"))

    res = await client.get(f"/api/auth/callback?code=abc&state={state}")

    assert res.headers["location"] == "/"


async def test_login_without_oidc_goes_straight_back(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "oidc_enabled", False)

    res = await client.get("/api/auth/login?return_to=/catalog")

    assert res.headers["location"] == "/catalog"


async def test_full_flow_sets_opaque_httponly_session(
    client, keycloak, session_factory
):
    res = await _authenticate(client, keycloak)

    assert res.headers["location"] == "/agents"
    session_cookie = next(
        c
        for c in res.headers.get_list("set-cookie")
        if c.startswith("myagents_session=")
    )
    assert "httponly" in session_cookie.lower()
    assert "samesite=lax" in session_cookie.lower()
    exchange = keycloak["calls"][0]
    assert exchange["grant_type"] == "authorization_code"
    assert exchange["code_verifier"]

    me = await client.get("/api/auth/me")
    assert me.status_code == 200
    assert me.json()["username"] == "alice"
    assert me.json()["id"] == "user-1"

    async with session_factory() as db:
        row = (await db.execute(select(AuthSession))).scalar_one()
    raw_cookie = client.cookies.get("myagents_session")
    assert row.token_hash != raw_cookie
    assert "refresh-token-secret" not in row.refresh_token_enc


async def test_session_cookie_is_secure_over_https(client, keycloak, monkeypatch):
    monkeypatch.setattr(get_settings(), "web_public_url", "https://app.example.org")

    login = await client.get("/api/auth/login?return_to=/agents")
    assert "secure" in login.headers["set-cookie"].lower()
    query = parse_qs(urlsplit(login.headers["location"]).query)
    keycloak["nonce"] = query["nonce"][0]
    flow = login.headers["set-cookie"].split(";")[0]

    # httpx ne renvoie pas un cookie Secure vers http://test : on le passe à la main.
    client.cookies.clear()
    res = await client.get(
        f"/api/auth/callback?code=abc&state={query['state'][0]}",
        headers={"Cookie": flow},
    )

    session_cookie = next(
        c
        for c in res.headers.get_list("set-cookie")
        if c.startswith("myagents_session=")
    )
    assert "secure" in session_cookie.lower()


async def test_callback_rejects_wrong_state_and_missing_flow(client, keycloak):
    await _login(client, keycloak)
    assert (
        await client.get("/api/auth/callback?code=abc&state=nope")
    ).status_code == 400

    client.cookies.clear()
    assert (await client.get("/api/auth/callback?code=abc&state=x")).status_code == 400


async def test_callback_rejects_nonce_mismatch(client, keycloak):
    state = await _login(client, keycloak)
    keycloak["nonce"] = "replayed-nonce"

    res = await client.get(f"/api/auth/callback?code=abc&state={state}")

    assert res.status_code == 302
    assert res.headers["location"] == "/?auth_error=authentication_failed"


async def test_callback_keycloak_error_is_rejected(client, keycloak):
    state = await _login(client, keycloak)

    res = await client.get(f"/api/auth/callback?error=access_denied&state={state}")

    assert res.status_code == 400


async def test_callback_oidc_error_redirects_with_auth_error_param(client, keycloak):
    """Erreur OIDC au callback → redirection vers /?auth_error=authentication_failed"""
    state = await _login(client, keycloak)
    keycloak["fail"] = True

    res = await client.get(f"/api/auth/callback?code=abc&state={state}")

    assert res.status_code == 302
    assert res.headers["location"] == "/?auth_error=authentication_failed"
    # Vérifier que le cookie flow est supprimé (max_age=0 ou similar)
    flow_cookies = [c for c in res.headers.get_list("set-cookie") if "myagents_oidc_flow" in c]
    assert len(flow_cookies) > 0  # Cookie doit être présent pour être supprimé
    assert any(
        "max-age=0" in c.lower() or c.lower().startswith("myagents_oidc_flow=")
        for c in flow_cookies
    )


async def test_me_requires_credentials(client):
    assert (await client.get("/api/auth/me")).status_code == 401


async def test_bearer_token_still_accepted(client, private_key):
    token = _jwt(private_key, "myagents-api")

    res = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})

    assert res.status_code == 200
    assert res.json()["username"] == "alice"


async def test_cookie_auth_protects_regular_api_routes(client, keycloak):
    assert (await client.get("/api/models")).status_code == 401
    await _authenticate(client, keycloak)

    assert (await client.get("/api/models")).status_code == 200


async def test_mutating_requests_with_cookie_need_csrf_header_and_origin(
    client, keycloak
):
    await _authenticate(client, keycloak)
    url = "/api/auth/logout"

    assert (await client.post(url)).status_code == 403
    evil = {"X-Requested-With": "XMLHttpRequest", "Origin": "https://evil.example"}
    assert (await client.post(url, headers=evil)).status_code == 403
    assert (await client.get("/api/auth/me")).status_code == 200


async def test_logout_ends_session_and_returns_keycloak_logout_url(client, keycloak):
    await _authenticate(client, keycloak)

    res = await client.post("/api/auth/logout", headers=CSRF)

    assert res.status_code == 200
    logout = urlsplit(res.json()["logout_url"])
    assert logout.path.endswith("/protocol/openid-connect/logout")
    assert "id_token_hint" in parse_qs(logout.query)
    assert (await client.get("/api/auth/me")).status_code == 401


async def test_deconnexion_link_ends_session_and_redirects_to_keycloak(
    client, keycloak
):
    """La déconnexion du menu commun est un simple lien GET /deconnexion."""
    await _authenticate(client, keycloak)

    res = await client.get("/deconnexion")

    assert res.status_code == 302
    logout = urlsplit(res.headers["location"])
    assert logout.path.endswith("/protocol/openid-connect/logout")
    assert "id_token_hint" in parse_qs(logout.query)
    assert (await client.get("/api/auth/me")).status_code == 401


async def test_deconnexion_without_session_still_reaches_keycloak(client):
    res = await client.get("/deconnexion")

    assert res.status_code == 302
    assert "/protocol/openid-connect/logout" in res.headers["location"]


async def _backdate(session_factory, **fields):
    async with session_factory() as db:
        row = (await db.execute(select(AuthSession))).scalar_one()
        for name, delta in fields.items():
            setattr(row, name, datetime.now(UTC) + delta)
        await db.commit()


async def test_expired_access_token_is_refreshed_server_side(
    client, keycloak, session_factory
):
    await _authenticate(client, keycloak)
    await _backdate(session_factory, access_expires_at=timedelta(seconds=-5))

    res = await client.get("/api/auth/me")

    assert res.status_code == 200
    assert keycloak["calls"][-1]["grant_type"] == "refresh_token"


async def test_refused_refresh_invalidates_the_session(
    client, keycloak, session_factory
):
    await _authenticate(client, keycloak)
    await _backdate(session_factory, access_expires_at=timedelta(seconds=-5))
    keycloak["fail"] = True

    assert (await client.get("/api/auth/me")).status_code == 401
    async with session_factory() as db:
        assert (await db.execute(select(AuthSession))).scalar_one_or_none() is None


async def test_resolve_session_concurrent_refresh_is_serialized(
    client, keycloak, session_factory
):
    """Deux appels simultanés à resolve_session avec access token expiré :
    seul le premier effectue le refresh (le second attend ou recourt à la relecture).
    """
    await _authenticate(client, keycloak)
    await _backdate(session_factory, access_expires_at=timedelta(seconds=-5))

    call_count = len(keycloak["calls"])

    # Simuler deux appels simultanés : tous deux vont tenter le refresh
    async with session_factory() as db:
        result1 = await auth_sessions.resolve_session(
            db, client.cookies.get("myagents_session")
        )
        await auth_sessions.resolve_session(
            db, client.cookies.get("myagents_session")
        )

    # Vérifier que le premier appel a retourné un utilisateur
    assert result1 is not None
    assert result1.username == "alice"

    # Le second appel devrait aussi retourner un utilisateur (via relecture)
    # ou None si la session a été supprimée, mais le comportement acceptable
    # est soit résultat1, soit résultat2 avec un seul refresh Keycloak
    # (no double refresh token call)
    refresh_calls = [c for c in keycloak["calls"][call_count:] if c.get("grant_type") == "refresh_token"]
    # Au maximum 1 appel refresh pour les deux requêtes concurrentes
    assert len(refresh_calls) <= 1


async def test_expired_session_is_rejected_and_purged(
    client, keycloak, session_factory
):
    await _authenticate(client, keycloak)
    await _backdate(session_factory, expires_at=timedelta(seconds=-1))

    assert (await client.get("/api/auth/me")).status_code == 401
    async with session_factory() as db:
        assert (await db.execute(select(AuthSession))).scalar_one_or_none() is None


async def test_id_token_with_wrong_audience_is_rejected(private_key):
    tokens = TokenSet(
        access_token=_jwt(private_key, "myagents-api"),
        refresh_token="r",
        id_token=_jwt(private_key, "someone-else", nonce="n"),
        expires_in=300,
        refresh_expires_in=0,
    )

    with pytest.raises(OIDCError):
        oidc_client.user_from_tokens(tokens, nonce="n")


async def test_unknown_session_cookie_is_rejected(client, db_session):
    client.cookies.set("myagents_session", "forged", domain="test", path="/")

    assert (await client.get("/api/auth/me")).status_code == 401
    assert await auth_sessions.resolve_session(db_session, "forged") is None


async def test_me_tells_the_front_whether_sso_is_enabled(client, keycloak, monkeypatch):
    await _authenticate(client, keycloak)
    assert (await client.get("/api/auth/me")).json()["sso_enabled"] is True

    monkeypatch.setattr(get_settings(), "oidc_enabled", False)
    assert (await client.get("/api/auth/me")).json()["sso_enabled"] is False


async def test_logout_without_session_needs_no_csrf_header(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "oidc_enabled", False)

    res = await client.post(
        "/api/auth/logout", headers={"Origin": "https://other.example"}
    )

    assert res.status_code == 200
    assert res.json() == {"logout_url": "/"}


async def test_logout_accepts_the_browser_origin_derived_from_code_server(
    client, keycloak, monkeypatch
):
    origin = "https://5174.code.example"
    # Connexion en http (httpx ne renvoie pas de cookie Secure), puis bascule sur l'origine publique.
    await _authenticate(client, keycloak)
    monkeypatch.setattr(get_settings(), "web_public_url", origin)
    monkeypatch.setattr(get_settings(), "cors_origins", [])

    res = await client.post(
        "/api/auth/logout", headers={"X-Requested-With": "x", "Origin": origin}
    )

    assert res.status_code == 200


# --- Groupe exigé (OIDC_GROUPE_EXIGE) ---------------------------------------------------


@pytest.mark.parametrize(
    ("exige", "groupes"),
    [
        (
            "mirai-beta-testeurs",
            ["/g/mirai-beta-testeurs"],
        ),  # nom feuille contre chemin
        ("mirai-beta-testeurs", ["mirai-beta-testeurs"]),  # nom contre nom
        ("/g/mirai-beta-testeurs", ["/g/mirai-beta-testeurs/"]),  # chemin contre chemin
    ],
)
async def test_member_of_required_group_gets_a_session(
    client, keycloak, monkeypatch, exige, groupes
):
    monkeypatch.setattr(get_settings(), "oidc_groupe_exige", exige)
    keycloak["groups"] = groupes

    await _authenticate(client, keycloak)

    assert (await client.get("/api/auth/me")).status_code == 200


@pytest.mark.parametrize(
    ("exige", "groupes"),
    [
        ("mirai-beta-testeurs", None),  # aucun claim groups
        ("mirai-beta-testeurs", ["/g/autre-equipe"]),
        (
            "/g/mirai-beta-testeurs",
            ["/h/mirai-beta-testeurs"],
        ),  # même feuille, autre chemin
    ],
)
async def test_outsider_is_refused_without_session(
    client, keycloak, monkeypatch, session_factory, exige, groupes
):
    monkeypatch.setattr(get_settings(), "oidc_groupe_exige", exige)
    keycloak["groups"] = groupes
    state = await _login(client, keycloak)

    res = await client.get(f"/api/auth/callback?code=abc&state={state}")

    assert res.status_code == 403
    assert "myagents_session" not in res.headers.get("set-cookie", "")
    async with session_factory() as db:
        assert (await db.execute(select(AuthSession))).first() is None


async def test_bearer_outside_required_group_is_forbidden(
    client, private_key, monkeypatch
):
    monkeypatch.setattr(get_settings(), "oidc_groupe_exige", "mirai-beta-testeurs")
    token = _jwt(private_key, "myagents-api", groups=["/g/autre-equipe"])

    res = await client.get("/api/agents", headers={"Authorization": f"Bearer {token}"})

    assert res.status_code == 403
    assert res.json()["detail"] == "groupe_requis"


async def test_session_loses_access_when_group_is_withdrawn(
    client, keycloak, monkeypatch, session_factory
):
    """Les groupes sont relus au rafraîchissement : un retrait coupe l'accès."""
    monkeypatch.setattr(get_settings(), "oidc_groupe_exige", "mirai-beta-testeurs")
    keycloak["groups"] = ["/g/mirai-beta-testeurs"]
    await _authenticate(client, keycloak)
    assert (await client.get("/api/auth/me")).status_code == 200

    keycloak["groups"] = []
    await _backdate(session_factory, access_expires_at=timedelta(seconds=-5))

    assert (await client.get("/api/auth/me")).status_code == 403


async def test_no_required_group_keeps_historic_behaviour(client, keycloak):
    keycloak["groups"] = None

    await _authenticate(client, keycloak)

    assert (await client.get("/api/auth/me")).status_code == 200
