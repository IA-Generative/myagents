"""Registry of built-in tools an agent creator can attach to their agent.

Mirrors `catalog.py` for models: a small static list the frontend renders as
checkboxes, plus a resolver turning selected ids into real LangChain tools.
"""

import logging
from collections.abc import Callable
from datetime import UTC, datetime

from langchain_core.tools import BaseTool, tool

from app.schemas.agent import ToolProfile

logger = logging.getLogger(__name__)


@tool
def current_datetime() -> str:
    """Renvoie la date et l'heure actuelles (UTC, ISO 8601)."""
    return datetime.now(UTC).isoformat()


TOOL_REGISTRY: dict[str, Callable[[], BaseTool]] = {
    "current_datetime": lambda: current_datetime,
}

AVAILABLE_TOOLS: list[ToolProfile] = [
    ToolProfile(
        id="current_datetime",
        label="Date et heure actuelles",
        description="Permet à l'agent de connaître la date et l'heure du jour.",
    ),
]


def resolve_tools(tool_ids: list[str], knowledge_ids: list[str]) -> list[BaseTool]:
    """Turn an agent's `tool_ids`/`knowledge_ids` config into bound LangChain tools."""
    tools: list[BaseTool] = []
    for tool_id in tool_ids:
        factory = TOOL_REGISTRY.get(tool_id)
        if factory is None:
            logger.warning("tool_id inconnu ignoré: %s", tool_id)
            continue
        tools.append(factory())

    if knowledge_ids:
        from app.llm.rag import build_retriever_tool

        tools.append(build_retriever_tool(knowledge_ids))

    return tools
