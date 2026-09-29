"""End-to-end API tests for the OpenAI-compatible /v1 endpoints (Open WebUI integration)."""

from unittest.mock import patch

from langchain_core.messages import AIMessage

from app.api.deps import require_openwebui_key
from app.llm.client import LlmClient
from app.main import app
from tests.fakes import FakeToolCallingModel
from tests.test_agents_api import _create_agent


async def test_models_endpoint_rejects_missing_key(client):
    with patch("app.api.deps.get_settings") as mock_settings:
        mock_settings.return_value.openwebui_api_key = "expected-secret"
        res = await client.get("/v1/models")
    assert res.status_code == 401


async def test_models_endpoint_rejects_wrong_key(client):
    with patch("app.api.deps.get_settings") as mock_settings:
        mock_settings.return_value.openwebui_api_key = "expected-secret"
        res = await client.get("/v1/models", headers={"Authorization": "Bearer wrong"})
    assert res.status_code == 401


async def test_models_endpoint_rejects_when_integration_disabled(client):
    with patch("app.api.deps.get_settings") as mock_settings:
        mock_settings.return_value.openwebui_api_key = ""
        res = await client.get(
            "/v1/models", headers={"Authorization": "Bearer anything"}
        )
    assert res.status_code == 401


async def test_models_endpoint_lists_all_non_archived_agents(client):
    app.dependency_overrides[require_openwebui_key] = lambda: None
    private_draft = await _create_agent(client, visibility="private", status="draft")
    published = await _create_agent(client, visibility="community", status="published")
    to_archive = await _create_agent(client, visibility="community", status="published")
    await client.delete(f"/api/agents/{to_archive['id']}")

    res = await client.get("/v1/models")
    assert res.status_code == 200
    ids = {m["id"] for m in res.json()["data"]}
    assert ids == {private_draft["id"], published["id"]}


async def test_chat_completions_returns_openai_shaped_response(client):
    app.dependency_overrides[require_openwebui_key] = lambda: None
    created = await _create_agent(client)
    fake_model = FakeToolCallingModel(responses=[AIMessage(content="Bonjour !")])

    with patch.object(LlmClient, "chat_model", return_value=fake_model):
        res = await client.post(
            "/v1/chat/completions",
            json={
                "model": created["id"],
                "messages": [{"role": "user", "content": "Salut"}],
            },
        )

    assert res.status_code == 200, res.text
    body = res.json()
    assert body["model"] == created["id"]
    assert body["choices"][0]["message"]["content"] == "Bonjour !"


async def test_chat_completions_unknown_model_returns_404(client):
    app.dependency_overrides[require_openwebui_key] = lambda: None
    res = await client.post(
        "/v1/chat/completions",
        json={"model": "00000000-0000-0000-0000-000000000000", "messages": []},
    )
    assert res.status_code == 404


async def test_chat_completions_stream_returns_sse(client):
    app.dependency_overrides[require_openwebui_key] = lambda: None
    created = await _create_agent(client)
    fake_model = FakeToolCallingModel(responses=[AIMessage(content="Bonjour !")])

    with patch.object(LlmClient, "chat_model", return_value=fake_model):
        res = await client.post(
            "/v1/chat/completions",
            json={
                "model": created["id"],
                "messages": [{"role": "user", "content": "Salut"}],
                "stream": True,
            },
        )

    assert res.status_code == 200
    assert "text/event-stream" in res.headers["content-type"]
    assert "Bonjour !" in res.text
    assert res.text.strip().endswith("data: [DONE]")
