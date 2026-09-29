"""Tests for the public catalog chat endpoint (no ownership required)."""

from unittest.mock import patch

from langchain_core.messages import AIMessage

from app.llm.client import LlmClient
from tests.fakes import FakeToolCallingModel

DRAFT_PAYLOAD = {
    "visibility": "community",
    "status": "published",
    "category": ["redaction"],
    "tags": [],
    "config": {
        "name": "Assistant public",
        "description": "Un agent partage",
        "category": "redaction",
        "system_prompt": "Tu es un assistant utile.",
        "greeting": "Bonjour",
        "examples": [],
        "model_id": "gpt-oss-120b",
        "temperature": 0.7,
    },
}


async def test_chat_with_catalog_agent_does_not_require_ownership(client):
    created = await client.post("/api/agents", json=DRAFT_PAYLOAD)
    agent_id = created.json()["id"]

    fake_model = FakeToolCallingModel(responses=[AIMessage(content="Bonjour a vous !")])
    with patch.object(LlmClient, "chat_model", return_value=fake_model):
        res = await client.post(
            f"/api/catalog/{agent_id}/chat",
            json={"messages": [{"role": "user", "content": "Salut"}]},
            headers={"X-User-Id": "other-user"},
        )

    assert res.status_code == 200, res.text
    assert res.json()["reply"] == "Bonjour a vous !"


async def test_chat_with_private_agent_via_catalog_is_not_found(client):
    payload = {**DRAFT_PAYLOAD, "visibility": "private", "status": "draft"}
    created = await client.post("/api/agents", json=payload)
    agent_id = created.json()["id"]

    res = await client.post(
        f"/api/catalog/{agent_id}/chat",
        json={"messages": [{"role": "user", "content": "Salut"}]},
        headers={"X-User-Id": "other-user"},
    )
    assert res.status_code == 404
