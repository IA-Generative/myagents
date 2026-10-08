"""LangChain agent-based execution runtime for published/drafted agents.

Unlike the plain LCEL chains in `chains.py` (used for the wizard's authoring
helpers), a running agent needs to optionally call tools and search its
knowledge bases mid-conversation. `create_agent` gives us that tool-calling
loop for free; when an agent has no tools configured it still goes through
the same code path (one LLM call, no loop), so there is a single place that
owns "how an agent answers a message".
"""

import logging
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass, field

import openai
from langchain.agents import create_agent

from app.llm.chains import history_messages, preview
from app.llm.client import (
    LlmClient,
    LlmModelNotFoundError,
    LlmParseError,
    LlmUnavailableError,
)
from app.llm.tools import resolve_tools
from app.schemas.agent import ChatMessage, ConfigSnapshot

logger = logging.getLogger(__name__)


@dataclass
class StreamEvent:
    """One event emitted during a streaming agent run."""

    type: str
    content: str = ""
    tool_name: str = ""
    tool_args: dict = field(default_factory=dict)
    tool_result: str = ""


def _is_model_not_found(exc: Exception) -> bool:
    msg = str(exc).lower()
    if isinstance(exc, openai.NotFoundError):
        return True
    if isinstance(exc, openai.BadRequestError):
        return (
            "model" in msg
            or "no service" in msg
            or "unsupported model" in msg
            or "not available" in msg
            or "unknown model" in msg
        )
    return False


def _build_agent(
    client: LlmClient, config: ConfigSnapshot, model: str, temperature: float
):
    tools = resolve_tools(config.tool_ids, config.knowledge_ids)
    agent = create_agent(
        client.chat_model(model, temperature),
        tools=tools,
        system_prompt=config.system_prompt,
    )
    return agent, tools


async def arun_agent_chat(
    client: LlmClient,
    config: ConfigSnapshot,
    history: list[ChatMessage],
    model: str,
    temperature: float,
) -> str:
    agent, tools = _build_agent(client, config, model, temperature)
    # Le prompt système de l'agent fait foi : on ignore les messages "system" fournis par l'appelant.
    history = [m for m in history if m.role != "system"]

    label = "agent_chat"
    logger.info("[%s] appel IA démarré (model=%s, tools=%d)", label, model, len(tools))
    start = time.perf_counter()
    try:
        result = await agent.ainvoke({"messages": history_messages(history)})
    except Exception as exc:
        duration_ms = (time.perf_counter() - start) * 1000
        if _is_model_not_found(exc):
            logger.warning(
                "[%s] modèle introuvable après %.0fms (model=%s): %s",
                label,
                duration_ms,
                model,
                preview(exc),
            )
            raise LlmModelNotFoundError(str(exc)) from exc
        logger.error(
            "[%s] LLM indisponible après %.0fms (model=%s): %s",
            label,
            duration_ms,
            model,
            preview(exc),
        )
        raise LlmUnavailableError(str(exc)) from exc
    duration_ms = (time.perf_counter() - start) * 1000

    messages = result.get("messages", [])
    reply = messages[-1].content if messages else ""
    if not isinstance(reply, str):
        raise LlmParseError(f"unexpected final message content type: {type(reply)}")

    logger.info("[%s] appel IA terminé en %.0fms (model=%s)", label, duration_ms, model)
    logger.debug("[%s] résultat: %s", label, preview(reply))
    return reply.strip()


async def arun_agent_chat_stream(
    client: LlmClient,
    config: ConfigSnapshot,
    history: list[ChatMessage],
    model: str,
    temperature: float,
) -> AsyncIterator[StreamEvent]:
    """Stream agent execution events: tokens, tool calls, tool results.

    Yields StreamEvent objects. The caller (guard + SSE endpoint) consumes
    them to display tokens live, show tool progress, and inspect output.
    """
    agent, tools = _build_agent(client, config, model, temperature)
    history = [m for m in history if m.role != "system"]

    label = "agent_chat_stream"
    logger.info("[%s] appel IA démarré (model=%s, tools=%d)", label, model, len(tools))
    start = time.perf_counter()
    _streaming_seen = False
    try:
        async for event in agent.astream_events(
            {"messages": history_messages(history)},
            version="v2",
        ):
            kind = event.get("event", "")
            data = event.get("data", {})

            if kind == "on_chat_model_stream":
                _streaming_seen = True
                chunk = data.get("chunk")
                if chunk is None:
                    continue
                content = getattr(chunk, "content", "")
                if isinstance(content, str) and content:
                    yield StreamEvent(type="token", content=content)

            elif kind == "on_chat_model_end" and not _streaming_seen:
                output = data.get("output")
                if output is None:
                    continue
                content = getattr(output, "content", output)
                if isinstance(content, str) and content:
                    yield StreamEvent(type="token", content=content)

            elif kind == "on_tool_start":
                tool_input = data.get("input", {})
                if not isinstance(tool_input, dict):
                    tool_input = {"input": str(tool_input)}
                yield StreamEvent(
                    type="tool_call",
                    tool_name=event.get("name", ""),
                    tool_args=tool_input,
                )

            elif kind == "on_tool_end":
                output = data.get("output", "")
                result_str = (
                    str(output.content) if hasattr(output, "content") else str(output)
                )
                yield StreamEvent(
                    type="tool_result",
                    tool_name=event.get("name", ""),
                    tool_result=result_str,
                )
    except Exception as exc:
        duration_ms = (time.perf_counter() - start) * 1000
        if _is_model_not_found(exc):
            logger.warning(
                "[%s] modèle introuvable après %.0fms (model=%s): %s",
                label,
                duration_ms,
                model,
                preview(exc),
            )
            raise LlmModelNotFoundError(str(exc)) from exc
        logger.error(
            "[%s] LLM indisponible après %.0fms (model=%s): %s",
            label,
            duration_ms,
            model,
            preview(exc),
        )
        raise LlmUnavailableError(str(exc)) from exc

    duration_ms = (time.perf_counter() - start) * 1000
    logger.info("[%s] stream terminé en %.0fms (model=%s)", label, duration_ms, model)
