"""LangChain LCEL chains implementing every agentic behaviour of the app.

Each chain is a `prompt | model | parser` runnable: LangChain owns prompt
templating, chat history injection and structured-output parsing (via Pydantic
schemas), instead of hand-rolled f-strings and regex JSON scraping.

Every call is traced through `_ainvoke` (label, model, duration, truncated
input/output previews) so LLM activity shows up clearly in the app logs.
"""

import json
import logging
import time

from langchain_core.exceptions import OutputParserException
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_core.output_parsers import PydanticOutputParser, StrOutputParser
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.runnables import Runnable

from app.core.config import get_settings
from app.llm.client import LlmClient, LlmParseError, LlmUnavailableError
from app.schemas.agent import (
    ChatMessage,
    ConfigSnapshot,
    OnboardingMessage,
    OnboardingTurn,
    RefineConfigResponse,
    SuggestStartersResponse,
)

logger = logging.getLogger(__name__)

_ROLE_TO_MESSAGE: dict[str, type[BaseMessage]] = {
    "system": SystemMessage,
    "user": HumanMessage,
    "assistant": AIMessage,
}


def history_messages(
    messages: list[ChatMessage] | list[OnboardingMessage],
) -> list[BaseMessage]:
    return [
        _ROLE_TO_MESSAGE.get(m.role, HumanMessage)(content=m.content) for m in messages
    ]


def preview(value: object, limit: int = 200) -> str:
    text = str(value).replace("\n", " ")
    return text if len(text) <= limit else f"{text[:limit]}…"


async def _ainvoke(chain: Runnable, payload: dict, *, label: str, model: str):
    """Invoke an LCEL chain, tracing it as one "appel IA" (start/success/failure + duration)."""
    logger.info("[%s] appel IA démarré (model=%s)", label, model)
    logger.debug("[%s] payload: %s", label, {k: preview(v) for k, v in payload.items()})
    start = time.perf_counter()
    try:
        result = await chain.ainvoke(payload)
    except OutputParserException as exc:
        duration_ms = (time.perf_counter() - start) * 1000
        logger.warning(
            "[%s] échec de parsing après %.0fms (model=%s): %s",
            label,
            duration_ms,
            model,
            preview(exc),
        )
        raise LlmParseError(str(exc)) from exc
    except Exception as exc:  # langchain/openai/httpx raise various error types
        duration_ms = (time.perf_counter() - start) * 1000
        logger.error(
            "[%s] LLM indisponible après %.0fms (model=%s): %s",
            label,
            duration_ms,
            model,
            preview(exc),
        )
        raise LlmUnavailableError(str(exc)) from exc
    duration_ms = (time.perf_counter() - start) * 1000
    logger.info("[%s] appel IA terminé en %.0fms (model=%s)", label, duration_ms, model)
    logger.debug("[%s] résultat: %s", label, preview(result))
    return result


# ---------------------------------------------------------------------------
# 2. "Aide-moi à écrire" / "Optimiser mon prompt" (plain text output).
# ---------------------------------------------------------------------------

_ASSIST_SYSTEM_PROMPT = """Tu es un assistant qui aide un utilisateur à rédiger un prompt \
système pour son propre agent IA. Propose un prompt structuré, clair, en français, avec des \
sections : rôle, public, ton, contraintes. Retourne UNIQUEMENT le prompt système proposé, sans \
préambule, sans commentaire, sans guillemets."""

_ASSIST_PROMPT = ChatPromptTemplate.from_messages(
    [("system", _ASSIST_SYSTEM_PROMPT), ("human", "{user_message}")]
)


async def assist_prompt(
    client: LlmClient, hints: dict[str, str], current_prompt: str
) -> str:
    model = get_settings().llm_assist_model
    chain = _ASSIST_PROMPT | client.chat_model(model, 0.5) | StrOutputParser()
    user_message = (
        f"Informations fournies par l'utilisateur :\n{json.dumps(hints, ensure_ascii=False)}\n\n"
        f"Prompt actuel (vide si nouveau) :\n{current_prompt or '(vide)'}\n\n"
        "Génère ou améliore le prompt système."
    )
    reply = await _ainvoke(
        chain, {"user_message": user_message}, label="assist_prompt", model=model
    )
    return reply.strip()


_OPTIMIZER_SYSTEM_PROMPT = """Tu es un assistant qui réécrit des prompts système pour des \
agents IA. Améliore la clarté, la structure, ajoute des garde-fous si nécessaire. Retourne \
UNIQUEMENT le prompt système réécrit, sans préambule, sans commentaire, sans guillemets."""

_OPTIMIZE_PROMPT = ChatPromptTemplate.from_messages(
    [("system", _OPTIMIZER_SYSTEM_PROMPT), ("human", "{prompt}")]
)


async def optimize_prompt(client: LlmClient, prompt: str) -> str:
    model = get_settings().llm_assist_model
    chain = _OPTIMIZE_PROMPT | client.chat_model(model, 0.4) | StrOutputParser()
    reply = await _ainvoke(
        chain, {"prompt": prompt}, label="optimize_prompt", model=model
    )
    return reply.strip() or prompt


# ---------------------------------------------------------------------------
# 3. Suggested greeting + starter examples (Pydantic-structured output).
# ---------------------------------------------------------------------------

_starters_parser = PydanticOutputParser(pydantic_object=SuggestStartersResponse)

_STARTERS_SYSTEM_PROMPT = """Tu es un assistant qui aide à mettre en service un agent IA. \
À partir du prompt système que l'utilisateur fournit, génère une amorce et des exemples de \
prompts que l'utilisateur final pourrait taper, représentatifs d'usages réalistes de l'agent.

{format_instructions}"""

_STARTERS_PROMPT = ChatPromptTemplate.from_messages(
    [("system", _STARTERS_SYSTEM_PROMPT), ("human", "{user_message}")]
).partial(format_instructions=_starters_parser.get_format_instructions())


async def suggest_starters(
    client: LlmClient, prompt: str, count: int
) -> SuggestStartersResponse:
    model = get_settings().llm_assist_model
    chain = _STARTERS_PROMPT | client.chat_model(model, 0.8) | _starters_parser
    user_message = (
        f"Voici le prompt système de l'agent :\n\n{prompt}\n\n"
        f"Génère l'amorce et {count} exemples de prompts."
    )
    return await _ainvoke(
        chain, {"user_message": user_message}, label="suggest_starters", model=model
    )


# ---------------------------------------------------------------------------
# 4. Onboarding chat: guided Q&A ending in a structured agent config.
# ---------------------------------------------------------------------------

_onboarding_parser = PydanticOutputParser(pydantic_object=OnboardingTurn)

_ONBOARDING_SYSTEM_PROMPT = """Tu es un assistant qui guide un utilisateur, par des questions \
successives, pour construire la configuration de son agent IA. Tu mènes un entretien court \
(5 à 6 échanges maximum) pour recueillir :

1. Le rôle principal de l'agent (que fait-il ?)
2. Le public visé (qui l'utilise ?)
3. Le ton souhaité (formel, pédagogique, bienveillant...)
4. Les contraintes ou garde-fous (ne pas inventer de sources, renvoyer vers un service, etc.)

Pose **une seule question à la fois** dans le champ "message", de manière naturelle et \
concise. Dans le champ "progress", liste les étapes déjà recueillies parmi : role, audience, \
tone, constraints. Tant que tu n'as pas recueilli assez d'informations, laisse "ready" à false \
et les autres champs vides. Dès que tu as assez d'informations, mets "ready" à true et remplis \
tous les champs en t'appuyant sur les réponses de l'utilisateur.

Quand "ready" est true :
- "name" : un nom court et descriptif (ex. « Rédacteur de notes administratives »).
- "category" : choisis parmi ces catégories existantes : rédaction, juridique, rh, sécurité, \
préfecture, communication. Si aucune ne correspond, utilise "autre".
- "system_prompt" : un prompt système structuré avec les sections Rôle, Public, Ton, \
Contraintes — rédigé comme une consigne directe à l'agent.
- "greeting" : un message d'accueil chaleureux qui présente l'agent et invite à interagir.
- "examples" : exactement 3 exemples de prompts qu'un utilisateur final pourrait taper.

IMPORTANT : ta réponse DOIT être un objet JSON valide conforme au schéma ci-dessous. Ne \
renvoie JAMAIS de texte brut ou de prose en dehors du JSON. Le champ "message" contient ta \
question ou remarque destinée à l'utilisateur.

{format_instructions}"""

_ONBOARDING_PROMPT = ChatPromptTemplate.from_messages(
    [("system", _ONBOARDING_SYSTEM_PROMPT), MessagesPlaceholder("history")]
).partial(format_instructions=_onboarding_parser.get_format_instructions())


async def onboarding_turn(
    client: LlmClient, history: list[OnboardingMessage]
) -> OnboardingTurn:
    model = get_settings().llm_onboarding_model
    chain = _ONBOARDING_PROMPT | client.chat_model(model, 0.6) | _onboarding_parser
    payload = {"history": history_messages(history[-40:])}
    try:
        return await _ainvoke(chain, payload, label="onboarding_turn", model=model)
    except LlmParseError:
        # Le modèle ne respecte pas les format_instructions (fréquent avec les
        # petits modèles instruct) : il répond en texte brut au lieu de JSON.
        # Plutôt que de renvoyer une erreur 502, on récupère le texte brut et
        # on l'utilise comme question de relance (ready=False). L'utilisateur
        # voit la question au lieu d'un message d'erreur.
        logger.warning("[onboarding_turn] parsing JSON échoué, repli sur texte brut")
        fallback_chain = (
            _ONBOARDING_PROMPT | client.chat_model(model, 0.6) | StrOutputParser()
        )
        raw = await _ainvoke(
            fallback_chain, payload, label="onboarding_turn (fallback)", model=model
        )
        return OnboardingTurn(message=raw.strip(), ready=False)


# ---------------------------------------------------------------------------
# 5. Refine config: adjust an agent config from user feedback.
# ---------------------------------------------------------------------------

_refine_parser = PydanticOutputParser(pydantic_object=RefineConfigResponse)

_REFINE_SYSTEM_PROMPT = """Tu es un assistant qui ajuste la configuration d'un agent IA à \
partir d'un feedback utilisateur. Tu reçois la config actuelle et un feedback (ex. « rends le \
ton moins formel », « ajoute une contrainte sur les sources »). Tu retourne la config complète \
ajustée en tenant compte du feedback, sans dégrader ce qui fonctionnait déjà.

Conserve la structure du system_prompt (Rôle, Public, Ton, Contraintes). Si le feedback \
concerne le nom, la description, le greeting ou les exemples, ajuste-les aussi. Le champ \
"message" contient un résumé court des changements effectués.

IMPORTANT : ta réponse DOIT être un objet JSON valide conforme au schéma ci-dessous. Ne \
renvoie JAMAIS de texte brut ou de prose en dehors du JSON.

{format_instructions}"""

_REFINE_PROMPT = ChatPromptTemplate.from_messages(
    [
        ("system", _REFINE_SYSTEM_PROMPT),
        ("human", "{config_json}\n\nFeedback : {feedback}"),
    ]
).partial(format_instructions=_refine_parser.get_format_instructions())


async def refine_config(
    client: LlmClient, config: ConfigSnapshot, feedback: str
) -> RefineConfigResponse:
    model = get_settings().llm_assist_model
    chain = _REFINE_PROMPT | client.chat_model(model, 0.4) | _refine_parser
    payload = {
        "config_json": config.model_dump_json(indent=2),
        "feedback": feedback,
    }
    try:
        return await _ainvoke(chain, payload, label="refine_config", model=model)
    except LlmParseError:
        # Même repli que pour onboarding_turn : si le modèle ne produit pas de JSON,
        # on retourne la config inchangée avec un message d'erreur user-friendly.
        logger.warning("[refine_config] parsing JSON échoué, config inchangée")
        return RefineConfigResponse(
            config=config,
            message="Je n'ai pas pu ajuster la configuration. Vous pouvez la modifier manuellement dans le wizard.",
        )
