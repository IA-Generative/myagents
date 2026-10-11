"""Interopérabilité avec le client MCP officiel (`mcp`, celui qu'embarque Open WebUI), en
processus : le client parle à l'application par un transport ASGI, sans réseau."""

from contextlib import asynccontextmanager

import httpx
import pytest
from httpx import ASGITransport
from langchain_core.messages import AIMessage
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

from app.db.session import get_db
from app.main import app
from tests.outils_capacites import entetes, fiche_prompt

pytestmark = pytest.mark.usefixtures("juge_definition_favorable")


def _fabrique(headers=None, timeout=None, auth=None):
    return httpx.AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers=headers,
        timeout=timeout or 30,
        auth=auth,
    )


@asynccontextmanager
async def session_officielle():
    """Session MCP officielle ouverte sur l'application (la base est celle de la fixture `client`)."""
    assert get_db in app.dependency_overrides
    async with (
        streamablehttp_client(
            "http://test/mcp", headers=entetes(), httpx_client_factory=_fabrique
        ) as (lecture, ecriture, _),
        ClientSession(lecture, ecriture) as session,
    ):
        await session.initialize()
        yield session


async def _publiee(client):
    res = await client.post(
        "/api/v2/capabilities", json=fiche_prompt(), headers=entetes()
    )
    cap = res.json()
    res = await client.post(
        f"/api/v2/capabilities/{cap['id']}/publish",
        json={"maturity": "general"},
        headers=entetes(),
    )
    assert res.status_code == 200, res.text
    return res.json()


async def test_initialize_et_list_tools(client):
    async with session_officielle() as session:
        outils = await session.list_tools()
    assert [t.name for t in outils.tools] == [
        "rechercher_capacites",
        "decrire_capacite",
        "executer_capacite",
    ]
    rechercher = outils.tools[0]
    assert rechercher.inputSchema["type"] == "object"
    assert (
        rechercher.annotations is not None
        and rechercher.annotations.readOnlyHint is True
    )


async def test_call_tool_epingle_et_meta_outil(client, fake_llm):
    cap = await _publiee(client)
    assert (
        await client.put(f"/api/v2/pins/{cap['name']}", headers=entetes())
    ).status_code == 200
    fake_llm.responses.append(AIMessage("Seconde réponse."))
    async with session_officielle() as session:
        outils = await session.list_tools()
        assert cap["name"] in [t.name for t in outils.tools]
        resultat = await session.call_tool(cap["name"], {"text": "Bonjour"})
        via_meta = await session.call_tool(
            "executer_capacite", {"name": cap["name"], "arguments": {"text": "Re"}}
        )
    assert resultat.isError is False
    assert resultat.content[0].text == "Réponse simulée."
    assert via_meta.isError is False
    assert via_meta.content[0].text == "Seconde réponse."


async def test_refus_rendu_comme_resultat_is_error(client):
    async with session_officielle() as session:
        resultat = await session.call_tool(
            "executer_capacite", {"name": "inexistante", "arguments": {}}
        )
    assert resultat.isError is True
    assert "introuvable" in resultat.content[0].text.lower()


async def test_prompts_officiels(client):
    cap = await _publiee(client)
    async with session_officielle() as session:
        prompts = await session.list_prompts()
        amorce = await session.get_prompt(cap["name"], {"text": "Bonjour"})
    assert cap["name"] in [p.name for p in prompts.prompts]
    assert amorce.messages[0].content.text == "Bonjour"
