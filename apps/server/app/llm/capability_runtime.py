"""Exécution d'une capacité `kind: prompt` : boucle d'appel d'outils maîtrisée par Mes agents.

À la différence de `agent_runtime` (qui délègue la boucle à `create_agent`), la boucle est
écrite ici pour appliquer la règle 4 de l'ADR : SEULES les dépendances déclarées sont appelables ;
un appel vers un autre outil est refusé, journalisé par l'appelant, et le modèle en est informé.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from app.llm.client import LlmClient

logger = logging.getLogger(__name__)

MAX_TOURS = 8

# Un appel d'outil à traiter : (nom, arguments) → texte rendu au modèle.
Executeur = Callable[[str, dict[str, Any]], Awaitable[str]]


def specification_outil(name: str, description: str, input_schema: dict) -> dict:
    """Définition d'outil au format OpenAI, telle que `bind_tools` l'accepte."""
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description[:1024],
            "parameters": input_schema or {"type": "object", "properties": {}},
        },
    }


def _texte(contenu: Any) -> str:
    if isinstance(contenu, str):
        return contenu
    if isinstance(contenu, list):
        return "".join(
            (b.get("text", "") if isinstance(b, dict) else str(b)) for b in contenu
        )
    return str(contenu or "")


async def arun_capability(
    client: LlmClient,
    *,
    system_prompt: str,
    user_text: str,
    tools: list[dict],
    model: str,
    temperature: float,
    executeur: Executeur,
) -> str:
    """Compose, appelle le modèle, exécute les appels d'outils par `executeur`, rend la réponse."""
    chat = client.chat_model(model, temperature)
    if tools:
        chat = chat.bind_tools(tools)
    messages: list = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_text),
    ]
    for _ in range(MAX_TOURS):
        reponse: AIMessage = await chat.ainvoke(messages)
        messages.append(reponse)
        appels = list(getattr(reponse, "tool_calls", None) or [])
        if not appels:
            return _texte(reponse.content).strip()
        for appel in appels:
            nom = str(appel.get("name", ""))
            args = appel.get("args") or {}
            if not isinstance(args, dict):
                args = {"arguments": args}
            contenu = await executeur(nom, args)
            messages.append(
                ToolMessage(content=contenu, tool_call_id=str(appel.get("id") or nom))
            )
    logger.warning("[capacite] boucle d'outils interrompue après %d tours", MAX_TOURS)
    return (
        _texte(messages[-1].content).strip()
        if isinstance(messages[-1], AIMessage)
        else ""
    )
