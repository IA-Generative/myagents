"""End-to-end API tests for agent CRUD, publishing, catalog, ratings, favorites."""

from unittest.mock import patch

from langchain_core.messages import AIMessage

from app.llm.client import LlmClient
from tests.fakes import FakeToolCallingModel

DRAFT_PAYLOAD = {
    "visibility": "private",
    "status": "draft",
    "category": ["redaction"],
    "tags": [],
    "config": {
        "name": "Assistant redaction",
        "description": "Aide a la redaction administrative",
        "category": "redaction",
        "system_prompt": "Tu es un assistant de redaction.",
        "greeting": "Bonjour, comment puis-je aider ?",
        "examples": [],
        "model_id": "gpt-oss-120b",
        "temperature": 0.7,
    },
}


async def _create_agent(client, **overrides):
    payload = {**DRAFT_PAYLOAD, **overrides}
    res = await client.post("/api/agents", json=payload)
    assert res.status_code == 200, res.text
    return res.json()


async def test_create_and_list_agent(client):
    created = await _create_agent(client)
    assert created["status"] == "draft"
    assert created["config"]["name"] == "Assistant redaction"

    res = await client.get("/api/agents")
    assert res.status_code == 200
    assert len(res.json()) == 1


async def test_update_agent_bumps_version(client):
    created = await _create_agent(client)
    agent_id = created["id"]

    update_payload = {**DRAFT_PAYLOAD, "status": "draft", "changelog": "essai"}
    update_payload["config"]["greeting"] = "Salut !"
    res = await client.put(f"/api/agents/{agent_id}", json=update_payload)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["version"] == 2
    assert body["config"]["greeting"] == "Salut !"


async def test_delete_agent_archives_it(client):
    created = await _create_agent(client)
    res = await client.delete(f"/api/agents/{created['id']}")
    assert res.status_code == 200
    assert res.json()["status"] == "archived"

    res = await client.get("/api/agents")
    assert res.json() == []


async def test_submit_makes_agent_visible_in_catalog(client):
    created = await _create_agent(client, visibility="community", status="draft")
    res = await client.post(f"/api/agents/{created['id']}/submit")
    assert res.status_code == 200
    assert res.json()["status"] == "submitted"

    catalog = await client.get("/api/catalog")
    assert len(catalog.json()) == 1


async def test_catalog_excludes_private_agents(client):
    await _create_agent(client, visibility="private", status="published")
    catalog = await client.get("/api/catalog")
    assert catalog.json() == []


async def test_rating_is_upserted_per_user(client):
    created = await _create_agent(client, visibility="community", status="published")
    agent_id = created["id"]

    res = await client.post(
        f"/api/ratings/{agent_id}", json={"score": 4, "comment": "bien"}
    )
    assert res.status_code == 200

    res = await client.post(
        f"/api/ratings/{agent_id}",
        json={"score": 5, "comment": "tres bien"},
        headers={"X-User-Id": "demo-user"},
    )
    assert res.status_code == 200

    ratings = (await client.get(f"/api/ratings/{agent_id}")).json()
    assert len(ratings) == 1
    assert ratings[0]["score"] == 5


async def test_favorite_add_and_remove(client):
    created = await _create_agent(client, visibility="community", status="published")
    agent_id = created["id"]

    res = await client.post(f"/api/favorites/{agent_id}")
    assert res.status_code == 200

    favorites = (await client.get("/api/favorites")).json()
    assert len(favorites) == 1

    res = await client.delete(f"/api/favorites/{agent_id}")
    assert res.status_code == 200

    favorites = (await client.get("/api/favorites")).json()
    assert favorites == []


async def test_fork_creates_independent_private_copy(client):
    created = await _create_agent(client, visibility="community", status="published")
    res = await client.post(f"/api/agents/{created['id']}/fork")
    assert res.status_code == 200
    forked = res.json()
    assert forked["id"] != created["id"]
    assert forked["visibility"] == "private"
    assert forked["status"] == "draft"


async def test_chat_with_agent_returns_llm_reply(client):
    created = await _create_agent(client)
    fake_model = FakeToolCallingModel(responses=[AIMessage(content="Bonjour !")])

    with patch.object(LlmClient, "chat_model", return_value=fake_model):
        res = await client.post(
            f"/api/agents/{created['id']}/chat",
            json={"messages": [{"role": "user", "content": "Salut"}]},
        )

    assert res.status_code == 200, res.text
    assert res.json() == {"reply": "Bonjour !"}
