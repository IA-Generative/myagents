"""Shared agent chat execution with LLM model fallback.

Extracted from ``agents.py`` and ``openai_compat.py`` to avoid duplication
and ensure both routes follow the same resolution chain and error handling.

Resolution chain (3 levels)::

    config.model_id -> agent.model_ref -> llm_default_model

The fallback is triggered on ``LlmModelNotFoundError`` and only when the
primary model differs from the default model.
"""

import logging
from typing import TYPE_CHECKING

from app.llm.agent_runtime import arun_agent_chat
from app.llm.client import LlmModelNotFoundError, LlmParseError, LlmUnavailableError
from app.schemas.agent import ChatMessage, ConfigSnapshot

if TYPE_CHECKING:
    from app.llm.client import LlmClient

logger = logging.getLogger(__name__)


class LlmModelResolutionError(Exception):
    """Raised when all model resolution attempts (primary + fallback) fail.

    This exception wraps the underlying LLM error (LlmModelNotFoundError,
    LlmUnavailableError, or LlmParseError) that occurred during fallback.
    """

    def __init__(self, original: Exception) -> None:
        super().__init__(str(original))
        self.original = original


async def run_agent_chat_with_model_fallback(
    client: LlmClient,  # type: ignore[name-defined]
    config: ConfigSnapshot,
    history: list[ChatMessage],
    temperature: float,
    primary_model: str,
    default_model: str,
) -> str:
    """Run an agent chat with automatic fallback to *default_model*.

    Parameters
    ----------
    client:
        LLM client already configured for the target endpoint.
    config:
        Agent configuration snapshot (tools, knowledge, system prompt).
    history:
        Conversation history messages.
    temperature:
        Sampling temperature passed to the LLM.
    primary_model:
        The first model to try (resolved by caller via
        ``config.model_id or agent.model_ref or default_model``).
    default_model:
        The fallback model from settings (``get_settings().llm_default_model``).

    Returns
    -------
    str
        The agent's reply text.

    Raises
    ------
    LlmModelResolutionError
        When the LLM call fails completely (both primary and fallback models).
    """
    try:
        reply = await arun_agent_chat(
            client,
            config,
            history=history,
            model=primary_model,
            temperature=temperature,
        )
        return reply
    except LlmModelNotFoundError as exc:
        if primary_model == default_model:
            logger.warning(
                "modele '%s' introuvable, skip fallback (identique au defaut)",
                primary_model,
            )
            raise LlmModelResolutionError(exc) from exc
        logger.warning(
            "modele '%s' introuvable, fallback sur '%s'", primary_model, default_model
        )
        try:
            reply = await arun_agent_chat(
                client,
                config,
                history=history,
                model=default_model,
                temperature=temperature,
            )
            return reply
        except (LlmUnavailableError, LlmParseError) as exc2:
            logger.error(
                "echec appel LLM: fallback sur '%s' echoué (model=%s): %s",
                default_model,
                primary_model,
                exc2,
            )
            raise LlmModelResolutionError(exc2) from exc2
    except (LlmUnavailableError, LlmParseError) as exc:
        # Hub injoignable, délai dépassé, réponse illisible : pas de repli (le défaut
        # passe par le même hub), mais une erreur que les routes savent traduire.
        raise LlmModelResolutionError(exc) from exc
