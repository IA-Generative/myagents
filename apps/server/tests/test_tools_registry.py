"""Unit tests for the built-in tools registry."""

from unittest.mock import patch

from langchain_core.tools import tool

from app.llm import rag
from app.llm.tools import resolve_tools


def test_resolve_tools_known_id_returns_bound_tool():
    tools = resolve_tools(["current_datetime"], [])
    assert len(tools) == 1
    assert tools[0].name == "current_datetime"


def test_resolve_tools_skips_unknown_id():
    tools = resolve_tools(["does_not_exist"], [])
    assert tools == []


def test_resolve_tools_without_ids_returns_empty_list():
    assert resolve_tools([], []) == []


def test_resolve_tools_adds_retriever_tool_when_knowledge_ids_given():
    @tool
    def fake_retriever_tool(query: str) -> str:
        """Fake."""
        return "ok"

    with patch.object(
        rag, "build_retriever_tool", return_value=fake_retriever_tool
    ) as mocked:
        tools = resolve_tools([], ["kb-1", "kb-2"])

    mocked.assert_called_once_with(["kb-1", "kb-2"])
    assert tools == [fake_retriever_tool]
