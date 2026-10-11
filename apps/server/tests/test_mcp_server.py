"""Serveur MCP Streamable HTTP sur /mcp (ADR §4.4, §10.1 point 4)."""

import asyncio
import json

import pytest

from app.core import security
from app.core.config import get_settings
from app.mcp import notifications
from tests.outils_capacites import (
    ACCEPT_MCP,
    ALICE,
    BOB,
    G1,
    G2,
    cle_rsa,
    entetes,
    fiche_prompt,
    jeton,
    jsonrpc,
    jwks_de,
)

pytestmark = pytest.mark.usefixtures("juge_definition_favorable")

A = {**entetes(), **ACCEPT_MCP}
B = {**entetes(sub=BOB, groupes=G2), **ACCEPT_MCP}
SOCLE = {**entetes(azp="socle", portees="mesagents:read"), **ACCEPT_MCP}


async def _publiee(client, h=entetes(), **kw):
    res = await client.post("/api/v2/capabilities", json=fiche_prompt(**kw), headers=h)
    assert res.status_code == 201, res.text
    cap = res.json()
    res = await client.post(
        f"/api/v2/capabilities/{cap['id']}/publish",
        json={"maturity": kw.pop("maturity", "general")},
        headers=h,
    )
    assert res.status_code == 200, res.text
    return res.json()


async def _rpc(client, method, params=None, h=A, id=1):
    res = await client.post("/mcp", json=jsonrpc(method, params, id), headers=h)
    return res


# --- Cycle de vie du protocole -----------------------------------------------------------------


async def test_initialize(client):
    res = await _rpc(
        client,
        "initialize",
        {
            "protocolVersion": "2025-06-18",
            "capabilities": {},
            "clientInfo": {"name": "t", "version": "1"},
        },
    )
    assert res.status_code == 200, res.text
    assert res.headers["content-type"].startswith("application/json")
    corps = res.json()
    assert corps["jsonrpc"] == "2.0" and corps["id"] == 1
    r = corps["result"]
    assert r["protocolVersion"] == "2025-06-18"
    assert r["capabilities"]["tools"]["listChanged"] is True
    assert "prompts" in r["capabilities"]
    assert r["serverInfo"]["name"] == "mes-agents"
    assert res.headers.get("mcp-session-id")
    assert res.headers["cache-control"] == "no-store"


async def test_initialize_version_inconnue_negociee(client):
    res = await _rpc(
        client,
        "initialize",
        {
            "protocolVersion": "1999-01-01",
            "capabilities": {},
            "clientInfo": {"name": "t", "version": "1"},
        },
    )
    assert res.json()["result"]["protocolVersion"] in (
        "2025-06-18",
        "2025-11-25",
        "2025-03-26",
    )


async def test_notification_initialized_202(client):
    res = await client.post(
        "/mcp", json=jsonrpc("notifications/initialized", id=None), headers=A
    )
    assert res.status_code == 202
    assert res.content in (b"", b"null")


async def test_ping(client):
    res = await _rpc(client, "ping")
    assert res.json()["result"] == {}


async def test_methode_inconnue_32601(client):
    res = await _rpc(client, "resources/list")
    assert res.status_code == 200
    assert res.json()["error"]["code"] == -32601


async def test_json_invalide_32700(client):
    res = await client.post(
        "/mcp",
        content=b"{pas du json",
        headers={**A, "Content-Type": "application/json"},
    )
    assert res.status_code == 400
    assert res.json()["error"]["code"] == -32700


async def test_lot_de_requetes(client):
    res = await client.post(
        "/mcp", json=[jsonrpc("ping", id=1), jsonrpc("ping", id=2)], headers=A
    )
    assert res.status_code == 200
    assert sorted(r["id"] for r in res.json()) == [1, 2]


async def test_delete_session_204(client):
    res = await client.delete("/mcp", headers={**A, "Mcp-Session-Id": "abc"})
    assert res.status_code == 204


# --- tools/list ---------------------------------------------------------------------------------


async def test_tools_list_meta_outils_et_epingles(client):
    cap = await _publiee(client)
    res = await _rpc(client, "tools/list")
    noms = [t["name"] for t in res.json()["result"]["tools"]]
    assert noms == ["rechercher_capacites", "decrire_capacite", "executer_capacite"]
    await client.put(f"/api/v2/pins/{cap['name']}", headers=entetes())
    res = await _rpc(client, "tools/list")
    outils = res.json()["result"]["tools"]
    assert [t["name"] for t in outils] == [
        "rechercher_capacites",
        "decrire_capacite",
        "executer_capacite",
        cap["name"],
    ]
    epingle = outils[3]
    assert epingle["inputSchema"]["required"] == ["text"]
    assert epingle["annotations"]["readOnlyHint"] is True
    assert epingle["_meta"]["hash"] == cap["versions"][0]["hash"]
    assert epingle["_meta"]["version"] == 1


async def test_c_a6_communaute_invisible_hors_groupe(client):
    cap = await _publiee(
        client, visibility="community", community_path=G1, maturity="beta"
    )
    await client.put(f"/api/v2/pins/{cap['name']}", headers=entetes())
    membre = {**entetes(sub="carol", groupes=G1), **ACCEPT_MCP}
    await client.put(
        f"/api/v2/pins/{cap['name']}", headers=entetes(sub="carol", groupes=G1)
    )
    assert cap["name"] in [
        t["name"]
        for t in (await _rpc(client, "tools/list", h=membre)).json()["result"]["tools"]
    ]
    res = await _rpc(client, "tools/list", h=B)
    assert cap["name"] not in [t["name"] for t in res.json()["result"]["tools"]]
    res = await _rpc(
        client, "tools/call", {"name": cap["name"], "arguments": {"text": "x"}}, h=B
    )
    r = res.json()["result"]
    assert r["isError"] is True and r["_meta"]["error"]["code"] == "not_found"
    res = await _rpc(
        client,
        "tools/call",
        {
            "name": "executer_capacite",
            "arguments": {"name": cap["name"], "arguments": {"text": "x"}},
        },
        h=B,
    )
    assert res.json()["result"]["_meta"]["error"]["code"] == "not_found"


async def test_c_a7_taille_constante(client, fake_llm):
    """10 puis 1 000 capacités publiées : tools/list identique (méta-outils + épinglés)."""
    for i in range(10):
        await _publiee(
            client,
            name=f"cap-{i:04d}",
            visibility="ministry",
            h=entetes(
                portees="mesagents:read mesagents:author mesagents:review",
                roles="mesagents-reviewer",
            ),
        )
    petit = (await _rpc(client, "tools/list")).json()["result"]["tools"]
    # Les 990 suivantes directement en base (le passage par l'API serait trop lent ici).
    from tests.outils_capacites import publier_en_masse

    await publier_en_masse(client, 990, prefixe="masse")
    grand = (await _rpc(client, "tools/list")).json()["result"]["tools"]
    assert len(petit) == len(grand) == 3
    assert json.dumps(petit, sort_keys=True) == json.dumps(grand, sort_keys=True)
    # Une capacité non épinglée reste atteignable en deux appels.
    r = (
        await _rpc(
            client,
            "tools/call",
            {"name": "rechercher_capacites", "arguments": {"query": "masse-0100"}},
        )
    ).json()["result"]
    assert r["isError"] is False
    trouvees = r["structuredContent"]["capabilities"]
    assert any(c["name"] == "masse-0100" for c in trouvees) and len(trouvees) <= 10
    r = (
        await _rpc(
            client,
            "tools/call",
            {
                "name": "executer_capacite",
                "arguments": {"name": "masse-0100", "arguments": {"text": "bonjour"}},
            },
        )
    ).json()["result"]
    assert r["isError"] is False
    assert r["content"][0]["text"] == "Réponse simulée."


async def test_contexte_azp_filtre_les_epingles(client, monkeypatch):
    monkeypatch.setattr(
        get_settings(),
        "mesagents_contextes_azp",
        {"socle": ["text"], "*": ["text", "email"]},
    )
    cap = await _publiee(
        client,
        name="classer-courriel",
        input_schema={
            "type": "object",
            "properties": {"email": {"type": "string"}},
            "required": ["email"],
        },
        examples=[{"input": {"email": "Bonjour"}, "expected": "autre"}],
    )
    await client.put(f"/api/v2/pins/{cap['name']}", headers=entetes())
    await client.put(
        f"/api/v2/pins/{cap['name']}",
        headers=entetes(azp="socle", portees="mesagents:read mesagents:author"),
    )
    assert cap["name"] in [
        t["name"] for t in (await _rpc(client, "tools/list")).json()["result"]["tools"]
    ]
    assert cap["name"] not in [
        t["name"]
        for t in (await _rpc(client, "tools/list", h=SOCLE)).json()["result"]["tools"]
    ]


# --- tools/call ------------------------------------------------------------------------------------


async def test_tools_call_epingle_execute_et_journalise(client, fake_llm):
    cap = await _publiee(client)
    await client.put(f"/api/v2/pins/{cap['name']}", headers=entetes())
    res = await _rpc(
        client, "tools/call", {"name": cap["name"], "arguments": {"text": "Bonjour"}}
    )
    r = res.json()["result"]
    assert r["isError"] is False
    assert r["content"] == [{"type": "text", "text": "Réponse simulée."}]
    assert (
        r["_meta"]["hash"] == cap["versions"][0]["hash"] and r["_meta"]["version"] == 1
    )
    assert r["_meta"]["generated"] is False
    runs = await client.get(f"/api/v2/capabilities/{cap['id']}/runs", headers=entetes())
    lignes = [json.loads(l) for l in runs.text.splitlines() if l.strip()]
    assert len(lignes) == 1
    ligne = lignes[0]
    assert (
        ligne["capability"] == cap["name"]
        and ligne["version"] == 1
        and ligne["hash"] == cap["versions"][0]["hash"]
    )
    assert ligne["sub"] == ALICE and ligne["azp"] == "surface-complete"
    assert ligne["scope_used"] == "mesagents:read" and ligne["status"] == "ok"
    assert (
        ligne["guard_in"] == "ok"
        and ligne["guard_out"] == "ok"
        and ligne["duration_ms"] >= 0
    )
    assert "Bonjour" not in runs.text and "Réponse simulée" not in runs.text


async def test_executer_capacite_passe_par_le_meme_chemin(client, fake_llm):
    cap = await _publiee(client)
    res = await _rpc(
        client,
        "tools/call",
        {
            "name": "executer_capacite",
            "arguments": {
                "name": cap["name"],
                "version": 1,
                "arguments": {"text": "Bonjour"},
            },
        },
    )
    r = res.json()["result"]
    assert r["isError"] is False and r["content"][0]["text"] == "Réponse simulée."
    runs = await client.get(f"/api/v2/capabilities/{cap['id']}/runs", headers=entetes())
    assert len([l for l in runs.text.splitlines() if l.strip()]) == 1


async def test_arguments_invalides_isError_invalid_request(client, fake_llm):
    cap = await _publiee(client)
    res = await _rpc(
        client,
        "tools/call",
        {
            "name": "executer_capacite",
            "arguments": {"name": cap["name"], "arguments": {}},
        },
    )
    r = res.json()["result"]
    assert r["isError"] is True and r["_meta"]["error"]["code"] == "invalid_request"
    assert "text" in r["content"][0]["text"]


async def test_sortie_generee_marquee(client, fake_llm):
    cap = await _publiee(
        client,
        grounding="open",
        examples=[{"input": {"text": str(i)}, "expected": "x"} for i in range(3)],
    )
    res = await _rpc(
        client,
        "tools/call",
        {
            "name": "executer_capacite",
            "arguments": {"name": cap["name"], "arguments": {"text": "x"}},
        },
    )
    assert res.json()["result"]["_meta"]["generated"] is True


async def test_c_a8_act_requis_sur_non_lecture_seule(client, fake_llm, monkeypatch):
    from tests.outils_capacites import fiche_mcp

    R = entetes(
        sub="revue",
        portees="mesagents:read mesagents:act mesagents:author mesagents:review",
        roles="mesagents-reviewer",
    )
    res = await client.post(
        "/api/v2/capabilities",
        json=fiche_mcp(
            name="outil.ecrit",
            visibility="ministry",
            annotations={
                "readOnlyHint": False,
                "destructiveHint": True,
                "idempotentHint": False,
                "openWorldHint": True,
            },
        ),
        headers=R,
    )
    outil = res.json()
    assert (
        await client.post(
            f"/api/v2/capabilities/{outil['id']}/publish",
            json={"maturity": "general"},
            headers=R,
        )
    ).status_code == 200
    res = await _rpc(
        client,
        "tools/call",
        {
            "name": "executer_capacite",
            "arguments": {"name": "outil.ecrit", "arguments": {"query": "x"}},
        },
        h=SOCLE,
    )
    r = res.json()["result"]
    assert r["isError"] is True and r["_meta"]["error"]["code"] == "scope_missing"
    assert "mesagents:act" in r["content"][0]["text"]
    # Avec la portée : le relais est tenté (le faux serveur MCP est injoignable → upstream_unavailable).
    from app.services import relais

    async def _relais(*a, **k):
        return relais.ResultatRelais(texte="relayé", is_error=False)

    monkeypatch.setattr(relais, "relayer_mcp", _relais)
    monkeypatch.setattr(
        get_settings(), "mesagents_relais_hotes_autorises", ["mcp-fake"]
    )
    res = await _rpc(
        client,
        "tools/call",
        {
            "name": "executer_capacite",
            "arguments": {"name": "outil.ecrit", "arguments": {"query": "x"}},
        },
    )
    r = res.json()["result"]
    assert r["isError"] is False, r
    assert r["content"][0]["text"] == "relayé"


async def test_c_a9_azp_suspendu_403_partout(client, monkeypatch):
    suspendu = {**entetes(azp="client-suspendu"), **ACCEPT_MCP}
    monkeypatch.setattr(get_settings(), "mesagents_azp_suspendus", ["client-suspendu"])
    for appel in (
        client.post("/mcp", json=jsonrpc("tools/list"), headers=suspendu),
        client.get("/api/v2/capabilities", headers=suspendu),
        client.put("/api/v2/pins/x", headers=suspendu),
        client.post("/api/v2/capabilities", json=fiche_prompt(), headers=suspendu),
    ):
        res = await appel
        assert res.status_code == 403, res.text
        assert res.json()["error"]["code"] == "forbidden"
    # Suspension par la table, sans redémarrage ni variable d'environnement.
    monkeypatch.setattr(get_settings(), "mesagents_azp_suspendus", [])
    assert (
        await client.get("/api/v2/capabilities", headers=suspendu)
    ).status_code == 200
    admin = entetes(
        sub="admin",
        roles="mesagents-reviewer",
        portees="mesagents:read mesagents:review",
    )
    res = await client.put(
        "/api/v2/admin/suspended-clients/client-suspendu",
        json={"reason": "test"},
        headers=admin,
    )
    assert res.status_code == 200
    assert (
        await client.get("/api/v2/capabilities", headers=suspendu)
    ).status_code == 403
    res = await client.delete(
        "/api/v2/admin/suspended-clients/client-suspendu", headers=admin
    )
    assert res.status_code == 200
    assert (
        await client.get("/api/v2/capabilities", headers=suspendu)
    ).status_code == 200


async def test_sans_portee_read_tout_refuse(client):
    sans = {**entetes(portees="openid profile"), **ACCEPT_MCP}
    res = await client.post("/mcp", json=jsonrpc("tools/list"), headers=sans)
    assert res.status_code == 403 and res.json()["error"]["code"] == "scope_missing"


# --- prompts/* ------------------------------------------------------------------------------------


async def test_prompts_list_et_get(client):
    cap = await _publiee(client)
    res = await _rpc(client, "prompts/list")
    prompts = res.json()["result"]["prompts"]
    p = next(p for p in prompts if p["name"] == cap["name"])
    assert p["title"] == cap["title"]
    assert [a["name"] for a in p["arguments"]] == ["text"]
    res = await _rpc(
        client, "prompts/get", {"name": cap["name"], "arguments": {"text": "Bonjour"}}
    )
    r = res.json()["result"]
    assert r["messages"][0]["role"] == "user"
    assert r["messages"][0]["content"] == {"type": "text", "text": "Bonjour"}
    res = await _rpc(client, "prompts/get", {"name": cap["name"]})
    assert res.json()["result"]["messages"][0]["content"]["text"] == "Exemple"
    res = await _rpc(client, "prompts/get", {"name": "inconnu"})
    assert res.json()["error"]["code"] == -32602


# --- Notifications ----------------------------------------------------------------------------------


async def test_get_mcp_exige_event_stream(client):
    res = await client.get("/mcp", headers=entetes())
    assert res.status_code == 405


async def test_list_changed_diffusee_a_la_personne(client):
    cap = await _publiee(client)
    file = notifications.diffuseur.abonner(ALICE)
    try:
        await client.put(f"/api/v2/pins/{cap['name']}", headers=entetes())
        message = await asyncio.wait_for(file.get(), timeout=2)
    finally:
        notifications.diffuseur.desabonner(ALICE, file)
    assert message["method"] == "notifications/tools/list_changed"


async def test_c_c3_publication_visible_par_le_groupe_et_notifiee(client):
    cap_res = await client.post(
        "/api/v2/capabilities",
        json=fiche_prompt(visibility="community", community_path=G1),
        headers=entetes(),
    )
    cap = cap_res.json()
    carol = "carol"
    file = notifications.diffuseur.abonner(carol)
    try:
        res = await client.post(
            f"/api/v2/capabilities/{cap['id']}/publish",
            json={"maturity": "beta"},
            headers=entetes(),
        )
        assert res.status_code == 200
        message = await asyncio.wait_for(file.get(), timeout=2)
    finally:
        notifications.diffuseur.desabonner(carol, file)
    assert message["method"] == "notifications/tools/list_changed"
    liste = await client.get(
        "/api/v2/capabilities", headers=entetes(sub=carol, groupes=G1)
    )
    assert cap["name"] in [t["name"] for t in liste.json()["tools"]]


async def test_flux_sse_porte_la_notification():
    """Le flux de GET /mcp transporte list_changed (le transport ASGI des tests ne diffuse pas en
    continu : on itère le générateur du flux ; le passage HTTP est prouvé en conformité, C-A11)."""
    from app.mcp.sse import flux_notifications

    flux = flux_notifications(ALICE, battement=0.2)
    premiere = await anext(flux)
    assert premiere.startswith(":")
    notifications.diffuseur.notifier_list_changed([ALICE])
    evenement = await asyncio.wait_for(anext(flux), timeout=2)
    assert evenement.startswith("event: message\ndata: ")
    assert "notifications/tools/list_changed" in evenement
    battement = await asyncio.wait_for(anext(flux), timeout=2)
    assert battement == ": ping\n\n"
    await flux.aclose()
    assert notifications.diffuseur.nombre_abonnes == 0


# --- Authentification SSO sur /mcp --------------------------------------------------------------------


@pytest.fixture
def sso(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "oidc_enabled", True)
    monkeypatch.setattr(s, "oidc_issuer", "http://kc.test/realms/preview")
    monkeypatch.setattr(s, "oidc_audience", "")
    monkeypatch.setattr(s, "public_base_url", "https://mesagents.example")
    cle = cle_rsa()
    monkeypatch.setattr(security, "_fetch_jwks", lambda force=False: jwks_de(cle))
    return cle


async def test_sans_jeton_401_avec_www_authenticate(client, sso):
    res = await client.post("/mcp", json=jsonrpc("tools/list"), headers=ACCEPT_MCP)
    assert res.status_code == 401
    assert res.json()["error"]["code"] == "invalid_token"
    assert (
        'resource_metadata="https://mesagents.example/.well-known/oauth-protected-resource/mcp"'
        in res.headers["www-authenticate"]
    )


async def test_jeton_sans_audience_403(client, sso):
    t = jeton(sso, aud="autre")
    res = await client.post(
        "/mcp",
        json=jsonrpc("tools/list"),
        headers={**ACCEPT_MCP, "Authorization": f"Bearer {t}"},
    )
    assert res.status_code == 403 and res.json()["error"]["code"] == "audience_mismatch"


async def test_jeton_valide_lit_azp_et_portees(client, sso):
    t = jeton(sso, azp="mirai-preview", scope="openid mesagents:read")
    res = await client.post(
        "/mcp",
        json=jsonrpc("tools/list"),
        headers={**ACCEPT_MCP, "Authorization": f"Bearer {t}"},
    )
    assert res.status_code == 200, res.text
    assert [x["name"] for x in res.json()["result"]["tools"]][:3] == [
        "rechercher_capacites",
        "decrire_capacite",
        "executer_capacite",
    ]
    t2 = jeton(sso, scope="openid profile")
    res = await client.post(
        "/mcp",
        json=jsonrpc("tools/list"),
        headers={**ACCEPT_MCP, "Authorization": f"Bearer {t2}"},
    )
    assert res.status_code == 403 and res.json()["error"]["code"] == "scope_missing"


async def test_jeton_sans_sub_401(client, sso):
    import time

    import jwt as pyjwt

    now = int(time.time())
    t = pyjwt.encode(
        {
            "iss": "http://kc.test/realms/preview",
            "aud": "mesagents",
            "iat": now,
            "exp": now + 60,
            "azp": "x",
            "scope": "mesagents:read",
        },
        sso,
        algorithm="RS256",
        headers={"kid": "k1"},
    )
    res = await client.post(
        "/mcp",
        json=jsonrpc("tools/list"),
        headers={**ACCEPT_MCP, "Authorization": f"Bearer {t}"},
    )
    assert res.status_code == 401
