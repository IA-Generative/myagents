"""Contrat d'agents MirAI : GET /api/v1/agents et /v1 avec un jeton utilisateur."""

import json
import time
from unittest.mock import patch

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt import PyJWKSet
from langchain_core.messages import AIMessage

from app.core import security
from app.core.config import get_settings
from app.llm.client import LlmClient
from app.models.enums import AgentStatus, Visibility
from app.schemas.agent import AgentCreate, ConfigSnapshot
from app.services import agents as agents_service
from tests.fakes import FakeToolCallingModel

ISSUER = "http://kc.test/realms/preview"
TESTEURS = "/g/mirai-beta-testeurs"
MOI = "moi"
COLLEGUE = "collegue"


async def _agent(db, creator, visibility, status, name, **config):
    payload = AgentCreate(
        visibility=visibility,
        status=status,
        category=["transverse"],
        config=ConfigSnapshot(name=name, system_prompt="Tu aides.", **config),
    )
    return await agents_service.create_agent(db, creator, payload)


@pytest.fixture
async def jeu(db_session):
    """Le jeu d'essai du contrat, vu par MOI (membre des testeurs, auteur d'un seul agent)."""
    a = {}
    a["mien"] = await _agent(
        db_session, MOI, Visibility.private, AgentStatus.draft, "Mon brouillon"
    )
    a["ministere"] = await _agent(
        db_session,
        COLLEGUE,
        Visibility.ministry,
        AgentStatus.published,
        "Relecteur",
        inputs=["text", "selection", "email"],
        outputs=["text", "replacement"],
    )
    a["communaute"] = await _agent(
        db_session,
        COLLEGUE,
        Visibility.community,
        AgentStatus.published,
        "Préparateur",
        community_path=TESTEURS,
        inputs=["meeting"],
    )
    a["autre_communaute"] = await _agent(
        db_session,
        COLLEGUE,
        Visibility.community,
        AgentStatus.published,
        "Autre",
        community_path="/g/autre",
    )
    a["prive"] = await _agent(
        db_session, COLLEGUE, Visibility.private, AgentStatus.published, "Privé"
    )
    a["brouillon"] = await _agent(
        db_session, COLLEGUE, Visibility.ministry, AgentStatus.draft, "Brouillon"
    )
    a["archive"] = await _agent(
        db_session, COLLEGUE, Visibility.ministry, AgentStatus.archived, "Archivé"
    )
    return {k: str(v.id) for k, v in a.items()}


DEV = {"X-User-ID": MOI, "X-User-Groups": TESTEURS}


# --- Sans SSO (dev) : la règle, les filtres, les en-têtes ----------------------------


async def test_liste_applique_la_regle_d_acces(client, jeu):
    res = await client.get("/api/v1/agents", headers=DEV)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["source"] == "mesagents"
    ids = [a["id"] for a in body["agents"]]
    # Les miens d'abord, puis les partagés du plus récent au plus ancien.
    assert ids == [jeu["mien"], jeu["communaute"], jeu["ministere"]]
    assert body["total"] == 3
    origines = {a["id"]: a["origin"] for a in body["agents"]}
    assert origines[jeu["mien"]] == "mine"
    assert origines[jeu["ministere"]] == "shared"


async def test_fiche_porte_les_champs_du_contrat(client, jeu):
    res = await client.get("/api/v1/agents", headers=DEV)
    fiche = next(a for a in res.json()["agents"] if a["id"] == jeu["ministere"])
    assert fiche["name"] == "Relecteur"
    assert fiche["inputs"] == ["text", "selection", "email"]
    assert fiche["outputs"] == ["text", "replacement"]
    assert fiche["model"] == jeu["ministere"]
    assert fiche["status"] == "published"
    assert fiche["visibility"] == "ministry"
    assert fiche["url"].startswith("http") and fiche["url"].endswith(jeu["ministere"])
    assert "updated_at" in fiche
    # Un instantané sans entrées déclarées vaut « text ».
    mien = next(a for a in res.json()["agents"] if a["id"] == jeu["mien"])
    assert mien["inputs"] == ["text"] and mien["outputs"] == ["text"]


async def test_filtre_sur_une_entree(client, jeu):
    res = await client.get("/api/v1/agents?input=meeting", headers=DEV)
    assert [a["id"] for a in res.json()["agents"]] == [jeu["communaute"]]
    assert res.json()["total"] == 1


async def test_limit_tronque_sans_changer_total(client, jeu):
    res = await client.get("/api/v1/agents?limit=1", headers=DEV)
    assert len(res.json()["agents"]) == 1
    assert res.json()["total"] == 3


@pytest.mark.parametrize("query", ["input=video", "limit=0", "limit=201"])
async def test_requete_invalide(client, jeu, query):
    res = await client.get(f"/api/v1/agents?{query}", headers=DEV)
    assert res.status_code == 400
    assert res.json()["error"]["code"] == "invalid_query"


async def test_hors_groupe_ne_voit_pas_la_communaute(client, jeu):
    res = await client.get(
        "/api/v1/agents", headers={"X-User-ID": MOI, "X-User-Groups": "/g/rh"}
    )
    assert [a["id"] for a in res.json()["agents"]] == [jeu["mien"], jeu["ministere"]]


async def test_reponses_en_no_store(client, jeu):
    res = await client.get("/api/v1/agents", headers=DEV)
    assert res.headers["cache-control"] == "no-store"


async def test_debit_limite(client, jeu, monkeypatch):
    monkeypatch.setattr(get_settings(), "contrat_rate_limit_per_minute", 2)
    await client.get("/api/v1/agents", headers=DEV)
    await client.get("/api/v1/agents", headers=DEV)
    res = await client.get("/api/v1/agents", headers=DEV)
    assert res.status_code == 429
    assert res.json()["error"]["code"] == "rate_limited"
    assert res.headers["retry-after"]


# --- CORS : préflight et en-têtes, aux seules origines des motifs -----------------------


@pytest.fixture
def origines(monkeypatch):
    monkeypatch.setattr(
        get_settings(),
        "contrat_origines",
        ["https://mysearch-pr-*.example", "https://monportail.example"],
    )


async def test_preflight_accepte_une_origine_du_motif(client, origines):
    res = await client.options(
        "/api/v1/agents",
        headers={
            "Origin": "https://mysearch-pr-12.example",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "authorization",
        },
    )
    assert res.status_code == 204
    assert (
        res.headers["access-control-allow-origin"] == "https://mysearch-pr-12.example"
    )
    assert "Authorization" in res.headers["access-control-allow-headers"]
    assert "POST" in res.headers["access-control-allow-methods"]
    assert "allow-credentials" not in str(res.headers).lower()
    assert res.headers["vary"] == "Origin"


async def test_preflight_refuse_une_origine_inconnue(client, origines):
    res = await client.options(
        "/v1/chat/completions",
        headers={
            "Origin": "https://evil.example",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert res.status_code == 403
    assert "access-control-allow-origin" not in res.headers


async def test_reponse_porte_l_origine_autorisee(client, origines, jeu):
    res = await client.get(
        "/api/v1/agents", headers={**DEV, "Origin": "https://monportail.example"}
    )
    assert res.headers["access-control-allow-origin"] == "https://monportail.example"
    assert res.headers["access-control-expose-headers"] == "Retry-After"


async def test_reponse_sans_origine_autorisee_reste_nue(client, origines, jeu):
    res = await client.get(
        "/api/v1/agents", headers={**DEV, "Origin": "https://evil.example"}
    )
    assert res.status_code == 200
    assert "access-control-allow-origin" not in res.headers


async def test_le_cors_du_contrat_ne_touche_pas_les_autres_routes(client, origines):
    res = await client.options(
        "/api/agents",
        headers={
            "Origin": "https://monportail.example",
            "Access-Control-Request-Method": "GET",
        },
    )
    # Le CORSMiddleware global ne connaît que les origines de la SPA.
    assert res.status_code == 400


# --- Avec SSO : jeton, audience, client appelant, groupe exigé --------------------------


@pytest.fixture
def sso(monkeypatch):
    settings = get_settings()
    for name, value in {
        "oidc_enabled": True,
        "oidc_issuer": ISSUER,
        "oidc_audience": "",
        "oidc_groupe_exige": "mirai-beta-testeurs",
        "contrat_audience": "mesagents",
        "contrat_clients_autorises": [],
    }.items():
        monkeypatch.setattr(settings, name, value)
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key()))
    jwk.update(kid="k1", alg="RS256", use="sig")
    monkeypatch.setattr(
        security, "_fetch_jwks", lambda force=False: PyJWKSet.from_dict({"keys": [jwk]})
    )
    return key


def _jeton(key, **extra) -> str:
    now = int(time.time())
    claims = {
        "iss": ISSUER,
        "aud": ["mesagents", "account"],
        "azp": "mirai-preview",
        "iat": now,
        "exp": now + 300,
        "sub": MOI,
        "preferred_username": "moi",
        "groups": [TESTEURS],
        **extra,
    }
    return jwt.encode(claims, key, algorithm="RS256", headers={"kid": "k1"})


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def test_jeton_valide_liste_selon_les_groupes(client, sso, jeu):
    res = await client.get("/api/v1/agents", headers=_bearer(_jeton(sso)))
    assert res.status_code == 200, res.text
    assert [a["id"] for a in res.json()["agents"]] == [
        jeu["mien"],
        jeu["communaute"],
        jeu["ministere"],
    ]


async def test_sans_jeton_401(client, sso):
    res = await client.get("/api/v1/agents")
    assert res.status_code == 401
    assert res.json()["error"]["code"] == "invalid_token"


async def test_jeton_sans_audience_403(client, sso):
    res = await client.get(
        "/api/v1/agents", headers=_bearer(_jeton(sso, aud="account"))
    )
    assert res.status_code == 403
    assert res.json()["error"]["code"] == "audience_mismatch"


async def test_audience_vide_desactive_le_controle(client, sso, jeu, monkeypatch):
    monkeypatch.setattr(get_settings(), "contrat_audience", "")
    res = await client.get(
        "/api/v1/agents", headers=_bearer(_jeton(sso, aud="account"))
    )
    assert res.status_code == 200


async def test_client_non_admis_403(client, sso, monkeypatch):
    monkeypatch.setattr(get_settings(), "contrat_clients_autorises", ["mysearch"])
    res = await client.get("/api/v1/agents", headers=_bearer(_jeton(sso)))
    assert res.status_code == 403
    assert res.json()["error"]["code"] == "audience_mismatch"
    res = await client.get(
        "/api/v1/agents", headers=_bearer(_jeton(sso, azp="mysearch"))
    )
    assert res.status_code == 200


async def test_jeton_sans_sub_401(client, sso):
    now = int(time.time())
    claims = {"iss": ISSUER, "aud": "mesagents", "iat": now, "exp": now + 300}
    token = jwt.encode(claims, sso, algorithm="RS256", headers={"kid": "k1"})
    res = await client.get("/api/v1/agents", headers=_bearer(token))
    assert res.status_code == 401


async def test_hors_du_groupe_exige_403(client, sso):
    res = await client.get(
        "/api/v1/agents", headers=_bearer(_jeton(sso, groups=["/g/rh"]))
    )
    assert res.status_code == 403
    assert res.json()["error"]["code"] == "forbidden"


async def test_jeton_expire_401(client, sso):
    now = int(time.time())
    res = await client.get(
        "/api/v1/agents", headers=_bearer(_jeton(sso, iat=now - 600, exp=now - 300))
    )
    assert res.status_code == 401


# --- /v1 avec un jeton utilisateur : même règle, format OpenAI ---------------------------


async def test_v1_models_avec_jeton_liste_selon_la_personne(client, sso, jeu):
    res = await client.get("/v1/models", headers=_bearer(_jeton(sso)))
    assert res.status_code == 200, res.text
    ids = {m["id"] for m in res.json()["data"]}
    assert ids == {jeu["mien"], jeu["ministere"], jeu["communaute"]}
    relecteur = next(m for m in res.json()["data"] if m["id"] == jeu["ministere"])
    assert relecteur["info"]["meta"]["description"] == ""


async def test_v1_models_avec_cle_partagee_liste_les_agents_partages(
    client, sso, jeu, monkeypatch
):
    monkeypatch.setattr(get_settings(), "openwebui_api_key", "cle-socle")
    res = await client.get("/v1/models", headers=_bearer("cle-socle"))
    assert res.status_code == 200
    ids = {m["id"] for m in res.json()["data"]}
    assert ids == {jeu["ministere"], jeu["communaute"], jeu["autre_communaute"]}


async def test_v1_models_jeton_sans_audience_403_openai(client, sso):
    res = await client.get("/v1/models", headers=_bearer(_jeton(sso, aud="account")))
    assert res.status_code == 403
    assert res.json()["error"]["code"] == "audience_mismatch"
    assert res.json()["error"]["type"] == "permission_error"


async def test_v1_chat_avec_jeton_lance_un_agent_accessible(client, sso, jeu):
    fake = FakeToolCallingModel(responses=[AIMessage(content="Voici la relecture.")])
    with patch.object(LlmClient, "chat_model", return_value=fake):
        res = await client.post(
            "/v1/chat/completions",
            headers=_bearer(_jeton(sso)),
            json={
                "model": jeu["communaute"],
                "messages": [
                    {"role": "user", "content": "Relis ceci.\n<<<\nbonjour\n>>>"}
                ],
            },
        )
    assert res.status_code == 200, res.text
    assert res.json()["choices"][0]["message"]["content"] == "Voici la relecture."


@pytest.mark.parametrize("cle", ["autre_communaute", "prive", "brouillon", "archive"])
async def test_v1_chat_avec_jeton_cache_un_agent_hors_de_portee(client, sso, jeu, cle):
    res = await client.post(
        "/v1/chat/completions",
        headers=_bearer(_jeton(sso)),
        json={"model": jeu[cle], "messages": [{"role": "user", "content": "Salut"}]},
    )
    assert res.status_code == 404
    assert res.json()["error"]["code"] == "model_not_found"


async def test_v1_chat_debit_par_personne(client, sso, jeu, monkeypatch):
    monkeypatch.setattr(get_settings(), "rate_limit_per_minute", 1)
    fake = FakeToolCallingModel(responses=[AIMessage(content="ok")])
    corps = {
        "model": jeu["ministere"],
        "messages": [{"role": "user", "content": "Salut"}],
    }
    with patch.object(LlmClient, "chat_model", return_value=fake):
        await client.post(
            "/v1/chat/completions", headers=_bearer(_jeton(sso)), json=corps
        )
        res = await client.post(
            "/v1/chat/completions", headers=_bearer(_jeton(sso)), json=corps
        )
    assert res.status_code == 429
    assert res.json()["error"]["code"] == "rate_limited"


# --- Le catalogue de l'application suit la même règle ------------------------------------


async def test_catalogue_filtre_les_communautes_par_groupe(client, jeu):
    res = await client.get("/api/catalog", headers=DEV)
    assert {a["id"] for a in res.json()} == {jeu["ministere"], jeu["communaute"]}
    res = await client.get(
        "/api/catalog", headers={"X-User-ID": MOI, "X-User-Groups": "/g/rh"}
    )
    assert {a["id"] for a in res.json()} == {jeu["ministere"]}


async def test_fiche_du_catalogue_hors_groupe_404(client, jeu):
    res = await client.get(
        f"/api/catalog/{jeu['communaute']}",
        headers={"X-User-ID": MOI, "X-User-Groups": "/g/rh"},
    )
    assert res.status_code == 404
