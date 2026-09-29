"""Unit tests for the LangChain agent execution runtime (no real LLM call)."""

from unittest.mock import patch

from langchain_core.messages import AIMessage

from app.llm.agent_runtime import arun_agent_chat
from app.llm.client import LlmClient
from app.schemas.agent import ChatMessage, ConfigSnapshot
from tests.fakes import FakeToolCallingModel


async def test_arun_agent_chat_without_tools_returns_final_reply():
    config = ConfigSnapshot(name="Test", system_prompt="Tu es utile.")
    fake_model = FakeToolCallingModel(responses=[AIMessage(content="Bonjour !")])

    with patch.object(LlmClient, "chat_model", return_value=fake_model):
        reply = await arun_agent_chat(
            LlmClient(),
            config,
            history=[ChatMessage(role="user", content="Salut")],
            model="gpt-oss-120b",
            temperature=0.7,
        )

    assert reply == "Bonjour !"


async def test_arun_agent_chat_invokes_configured_tool():
    config = ConfigSnapshot(
        name="Test",
        system_prompt="Tu es utile.",
        tool_ids=["current_datetime"],
    )
    fake_model = FakeToolCallingModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[{"name": "current_datetime", "args": {}, "id": "call1"}],
            ),
            AIMessage(content="Il est l'heure indiquee par l'outil."),
        ]
    )

    with patch.object(LlmClient, "chat_model", return_value=fake_model):
        reply = await arun_agent_chat(
            LlmClient(),
            config,
            history=[ChatMessage(role="user", content="Quelle heure est-il ?")],
            model="gpt-oss-120b",
            temperature=0.7,
        )

    assert reply == "Il est l'heure indiquee par l'outil."


async def test_arun_agent_chat_ignores_unknown_tool_id():
    config = ConfigSnapshot(
        name="Test", system_prompt="Tu es utile.", tool_ids=["does_not_exist"]
    )
    fake_model = FakeToolCallingModel(responses=[AIMessage(content="Ok")])

    with patch.object(LlmClient, "chat_model", return_value=fake_model):
        reply = await arun_agent_chat(
            LlmClient(),
            config,
            history=[ChatMessage(role="user", content="Salut")],
            model="gpt-oss-120b",
            temperature=0.7,
        )

    assert reply == "Ok"
