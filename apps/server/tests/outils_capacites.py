"""Aides partagées par les tests du chantier « capacités gouvernées » (ADR Mes agents).

Identité en mode dev (OIDC désactivé) : en-têtes `X-User-*` lus par `app.api.deps_v2`.
Jetons signés pour les tests SSO : clé RSA locale, JWKS monkeypatché comme dans
`tests/test_auth_bff.py`.
"""

import json
import time

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt import PyJWKSet

ISSUER = "http://kc.test/realms/preview"
G1 = "/g/G1"
G2 = "/g/G2"
ALICE = "alice-sub"
BOB = "bob-sub"
REVUE = "revue-sub"

TOUTES_PORTEES = "mesagents:read mesagents:act mesagents:author mesagents:review"


def entetes(
    sub: str = ALICE,
    groupes: str = G1,
    azp: str = "surface-complete",
    portees: str = "mesagents:read mesagents:act mesagents:author",
    roles: str = "",
) -> dict[str, str]:
    """En-têtes d'identité du mode dev (sans SSO)."""
    h = {
        "X-User-ID": sub,
        "X-User-Groups": groupes,
        "X-User-Azp": azp,
        "X-User-Scopes": portees,
    }
    if roles:
        h["X-User-Roles"] = roles
    return h


def fiche_prompt(
    name: str = "reformuler-texte",
    *,
    prompt: str = "Tu reformules le texte fourni en langage clair.",
    grounding: str = "input",
    examples: list | None = None,
    dependencies: list | None = None,
    visibility: str = "private",
    community_path: str | None = None,
    annotations: dict | None = None,
    **extra,
) -> dict:
    """Corps de création d'une capacité `kind: prompt` (POST /api/v2/capabilities)."""
    corps = {
        "name": name,
        "kind": "prompt",
        "title": "Reformuler un texte",
        "description": "Reformule le texte fourni en langage clair, sans en changer le sens.",
        "input_schema": {
            "type": "object",
            "properties": {"text": {"type": "string", "description": "Le texte"}},
            "required": ["text"],
        },
        "definition": {"prompt": prompt, "model": "chat", "temperature": 0.2},
        "dependencies": dependencies or [],
        "grounding": grounding,
        "visibility": visibility,
        "community_path": community_path,
        "examples": examples
        if examples is not None
        else [{"input": {"text": "Exemple"}, "expected": "Exemple reformulé"}],
    }
    if annotations is not None:
        corps["annotations"] = annotations
    corps.update(extra)
    return corps


def fiche_mcp(
    name: str = "mcp-fake.rechercher",
    *,
    endpoint: str = "http://mcp-fake:8000/mcp",
    tool: str = "rechercher",
    identity: str = "user",
    annotations: dict | None = None,
    visibility: str = "private",
    **extra,
) -> dict:
    """Corps de création d'une capacité `kind: mcp` (outil externe relayé)."""
    corps = {
        "name": name,
        "kind": "mcp",
        "title": "Recherche (outil externe)",
        "description": "Relaie une recherche vers un serveur MCP externe.",
        "input_schema": {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
        "definition": {"endpoint": endpoint, "tool": tool, "identity": identity},
        "dependencies": [],
        "grounding": "input",
        "visibility": visibility,
        "annotations": annotations
        or {
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
        "examples": [],
    }
    corps.update(extra)
    return corps


def jsonrpc(method: str, params: dict | None = None, id: int | str | None = 1) -> dict:
    corps: dict = {"jsonrpc": "2.0", "method": method}
    if params is not None:
        corps["params"] = params
    if id is not None:
        corps["id"] = id
    return corps


ACCEPT_MCP = {"Accept": "application/json, text/event-stream"}


def cle_rsa():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def jwks_de(cle) -> PyJWKSet:
    jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(cle.public_key()))
    jwk.update(kid="k1", alg="RS256", use="sig")
    return PyJWKSet.from_dict({"keys": [jwk]})


def jeton(
    cle,
    *,
    sub: str = ALICE,
    aud: str | list[str] = "mesagents",
    azp: str = "surface-complete",
    scope: str = "openid profile mesagents:read mesagents:act mesagents:author",
    groups: list[str] | None = None,
    roles: list[str] | None = None,
    iss: str = ISSUER,
    exp_dans: int = 300,
    **extra,
) -> str:
    now = int(time.time())
    claims = {
        "iss": iss,
        "aud": aud,
        "iat": now,
        "exp": now + exp_dans,
        "sub": sub,
        "azp": azp,
        "scope": scope,
        "preferred_username": sub,
        "groups": groups if groups is not None else [G1],
        "realm_access": {"roles": roles or ["user"]},
        **extra,
    }
    return jwt.encode(claims, cle, algorithm="RS256", headers={"kid": "k1"})


async def publier_en_masse(client, nombre: int, *, prefixe: str = "masse") -> None:
    """Crée `nombre` capacités publiées `ministry` directement en base (fixture de volume, C-A7)."""
    from app.core.hashing import hash_canonique
    from app.db.session import get_db
    from app.main import app
    from app.models.capability import Capability, CapabilityVersion

    get_session = app.dependency_overrides[get_db]
    schema = {
        "type": "object",
        "properties": {"text": {"type": "string"}},
        "required": ["text"],
    }
    async for db in get_session():
        for i in range(nombre):
            name = f"{prefixe}-{i:04d}"
            definition = {
                "prompt": f"Tu es la capacité {name}.",
                "model": "chat",
                "temperature": 0.2,
            }
            cap = Capability(
                name=name,
                kind="prompt",
                title=f"Capacité {name}",
                description=f"Capacité de masse {name}.",
                input_schema=schema,
                definition=definition,
                dependencies=[],
                grounding="input",
                annotations={
                    "readOnlyHint": True,
                    "destructiveHint": False,
                    "idempotentHint": True,
                    "openWorldHint": False,
                },
                examples=[],
                visibility="ministry",
                owner_sub="masse",
                status="published",
                current_version=1,
            )
            db.add(cap)
            await db.flush()
            db.add(
                CapabilityVersion(
                    capability_id=cap.id,
                    version=1,
                    maturity="general",
                    hash=hash_canonique(definition, schema, []),
                    title=cap.title,
                    description=cap.description,
                    definition=definition,
                    input_schema=schema,
                    dependencies=[],
                    annotations=cap.annotations,
                    grounding="input",
                    examples=[],
                    published_by="masse",
                    published_from="test",
                    guard_verdict="favorable",
                    guard_ruleset_version="test",
                    guard_details=[],
                )
            )
        await db.commit()
        break
