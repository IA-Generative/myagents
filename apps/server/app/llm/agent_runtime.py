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

import openai
from langchain.agents import create_agent

from app.llm.chains import history_messages, preview
from app.llm.client import LlmClient, LlmModelNotFoundError, LlmParseError, LlmUnavailableError
from app.llm.tools import resolve_tools
from app.schemas.agent import ChatMessage, ConfigSnapshot

logger = logging.getLogger(__name__)


def _is_model_not_found(exc: Exception) -> bool:
    msg = str(exc).lower()
    logger.info(
        "[agent_runtime] _is_model_not_found: exc_type=%s exc_msg=%s",
        type(exc).__name__, msg,
    )
    if isinstance(exc, openai.NotFoundError):
        return True
    if isinstance(exc, openai.BadRequestError):
        return "model" in msg or "no service" in msg or "unsupported model" in msg or "not available" in msg or "unknown model" in msg
    return False


async def arun_agent_chat(
    client: LlmClient,
    config: ConfigSnapshot,
    history: list[ChatMessage],
    model: str,
    temperature: float,
) -> str:
    tools = resolve_tools(config.tool_ids, config.knowledge_ids)
    # Le prompt système de l'agent fait foi : on ignore les messages "system" fournis par l'appelant.
    history = [m for m in history if m.role != "system"]
    agent = create_agent(
        client.chat_model(model, temperature),
        tools=tools,
        system_prompt=config.system_prompt,
    )

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
                label, duration_ms, model, preview(exc),
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
