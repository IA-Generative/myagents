"""Application de la garde anti-prompt-injection aux routes, et journal d'audit.

Chaque route qui touche un LLM ou un prompt passe par ici :

- `check_input`  : couche 1 (inspection de l'entrée), 422 `blocked_input` ;
- `check_output` : couche 3 (heuristiques + LLM-juge fail-closed), 422 `blocked_output` ;
- `guarded_agent_chat` : chaîne complète d'une conversation avec un agent
  (entrée, prompt durci + canari, sortie + juge).

Tout signal déclenché (bloquant ou advisory) est journalisé : log `[prompt-guard]`
sans contenu, puis ligne `guard_events` en best-effort (un échec d'écriture ne
casse jamais la requête : le blocage prime sur l'audit).
"""

import contextlib
import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Literal

from sqlalchemy.ext.asyncio import AsyncSession

from app.llm.agent_runtime import StreamEvent
from app.llm.guard import (
    BLOCK_MESSAGE_OUTPUT,
    BLOCK_MESSAGE_USER_INPUT,
    DEFAULT_GUARD_CONFIG,
    GuardResult,
    Signal,
    StreamingOutputInspector,
    harden_system_prompt,
    inspect_input,
    inspect_output,
    judge_output,
    log_guard_event,
    make_canary,
)
from app.llm.guard.core import Role, Stage, fired_signals, highest_severity
from app.models.guard_event import GuardEvent
from app.schemas.agent import ChatMessage, ConfigSnapshot

logger = logging.getLogger(__name__)

GuardErrorCode = Literal["blocked_input", "blocked_output"]

# Persona par défaut d'un agent sans prompt système (comme en production).
DEFAULT_PERSONA = "Tu es un assistant."


class GuardBlockedError(Exception):
    """Contenu refusé par la garde ; rendu en 422 par l'application."""

    def __init__(self, code: GuardErrorCode, message: str) -> None:
        super().__init__(code)
        self.code = code
        self.message = message


async def record_guard_event(
    db: AsyncSession | None,
    *,
    route: str,
    stage: Stage,
    signals: list[Signal],
    user_id: str | None = None,
    role: Role | None = None,
) -> None:
    """Journalise les signaux déclenchés (log + table `guard_events`), sans jamais lever."""
    log_guard_event(
        route=route, stage=stage, signals=signals, user_id=user_id, role=role
    )
    fired = fired_signals(signals)
    if not fired or db is None:
        return
    try:
        db.add(
            GuardEvent(
                user_id=user_id[:255] if user_id else None,
                route=route,
                stage=stage,
                role=role,
                severity=highest_severity(fired),
                signals=[
                    {"source": s.source, "severity": s.severity, "reason": s.reason}
                    for s in fired
                ],
            )
        )
        await db.commit()
    except Exception as exc:  # noqa: BLE001 — l'audit ne doit jamais casser la requête
        logger.error(
            "[guard-audit] échec de persistance GuardEvent (non bloquant): %s",
            type(exc).__name__,
        )
        # La session est peut-être déjà inutilisable : on n'insiste pas.
        with contextlib.suppress(Exception):
            await db.rollback()


async def check_input(
    db: AsyncSession | None,
    *,
    route: str,
    text: str,
    role: Role,
    block_message: str,
    user_id: str | None = None,
    stage: Stage = "input",
) -> GuardResult:
    """Couche 1 : bloque l'entrée avant tout appel LLM (anomalie en posture audit)."""
    result = inspect_input(text, role, anomaly=DEFAULT_GUARD_CONFIG.anomaly)
    if fired_signals(result.signals):
        await record_guard_event(
            db,
            route=route,
            stage=stage,
            signals=result.signals,
            user_id=user_id,
            role=role,
        )
    if result.blocked:
        raise GuardBlockedError("blocked_input", block_message)
    return result


async def check_output(
    db: AsyncSession | None,
    *,
    route: str,
    text: str,
    user_id: str | None = None,
    role: Role | None = None,
    canary: str | None = None,
) -> None:
    """Couche 3 : heuristiques (keylogger, canari) puis LLM-juge fail-closed."""
    heuristics = inspect_output(text, canary=canary)
    verdict = await judge_output(text)
    signals = [
        *heuristics.signals,
        Signal("judge", verdict.complied, verdict.reason, "medium"),
    ]
    if fired_signals(signals):
        await record_guard_event(
            db,
            route=route,
            stage="output",
            signals=signals,
            user_id=user_id,
            role=role,
        )
        # Caviardage total : la réponse n'est ni renvoyée ni conservée.
        raise GuardBlockedError("blocked_output", BLOCK_MESSAGE_OUTPUT)


def last_message_content(messages: list[ChatMessage]) -> str:
    """Dernier message transmis au modèle (les messages « system » sont ignorés par le runtime)."""
    for message in reversed(messages):
        if message.role != "system":
            return message.content
    return ""


async def guarded_agent_chat(
    db: AsyncSession | None,
    *,
    route: str,
    user_id: str | None,
    config: ConfigSnapshot,
    history: list[ChatMessage],
    run: Callable[[ConfigSnapshot], Awaitable[str]],
) -> str:
    """Conversation avec un agent sous les trois couches de la garde.

    `run` exécute l'agent (boucle d'outils, recherche dans les connaissances) avec
    la configuration durcie ; seule sa réponse finale est contrôlée en sortie.
    """
    await check_input(
        db,
        route=route,
        text=last_message_content(history),
        role="user",
        block_message=BLOCK_MESSAGE_USER_INPUT,
        user_id=user_id,
    )

    canary = make_canary()
    hardened = config.model_copy(
        update={
            "system_prompt": harden_system_prompt(
                config.system_prompt or DEFAULT_PERSONA, canary
            )
        }
    )
    reply = await run(hardened)

    await check_output(
        db, route=route, text=reply, user_id=user_id, role="user", canary=canary
    )
    return reply


async def guarded_agent_chat_stream(
    db: AsyncSession | None,
    *,
    route: str,
    user_id: str | None,
    config: ConfigSnapshot,
    history: list[ChatMessage],
    run: Callable[[ConfigSnapshot], AsyncIterator[StreamEvent]],
    skip_input_check: bool = False,
) -> AsyncIterator[StreamEvent]:
    """Conversation avec streaming sous les trois couches de la garde.

    Couche 1 (entrée) et couche 2 (durcissement + canari) identiques à
    ``guarded_agent_chat``. La différence est la couche 3 : les tokens sont
    inspectés au fil de l'eau via ``StreamingOutputInspector`` (heuristiques
    keylogger + fuite canari), puis le LLM-juge est appelé sur le texte
    complet assemblé après la fin du stream.

    .. note::
        Les jetons sont émis au client avant le verdict du juge LLM. Les
        heuristiques en vol (signatures keylogger, fuite du canari) interceptent
        les contenus manifestement hostiles pendant l'émission, mais le juge
        ne se prononce qu'après. S'il refuse, un événement ``blocked`` est émis
        (``finish_reason: content_filter`` côté OpenAI) et le message n'est pas
        persisté. La route ``/v1/chat/completions`` ne diffuse jamais les jetons
        avant le verdict (voir ``openai_compat._sse_full_reply``) ; cette
        fonction n'est utilisée que par le streaming interne (``/api/agents``
        et ``/api/catalog``), où les étapes d'outils sont affichées en direct.
    """
    if not skip_input_check:
        await check_input(
            db,
            route=route,
            text=last_message_content(history),
            role="user",
            block_message=BLOCK_MESSAGE_USER_INPUT,
            user_id=user_id,
        )

    canary = make_canary()
    hardened = config.model_copy(
        update={
            "system_prompt": harden_system_prompt(
                config.system_prompt or DEFAULT_PERSONA, canary
            )
        }
    )

    inspector = StreamingOutputInspector(canary=canary)
    assembled: list[str] = []

    async for event in run(hardened):
        if event.type == "token":
            inspector.push(event.content)
            assembled.append(event.content)
            if inspector.done().blocked:
                await record_guard_event(
                    db,
                    route=route,
                    stage="output",
                    signals=inspector.done().signals,
                    user_id=user_id,
                    role="user",
                )
                yield StreamEvent(type="blocked", content=BLOCK_MESSAGE_OUTPUT)
                return
            yield event
        elif event.type == "tool_result" and event.tool_result:
            inspector.push(event.tool_result)
            if inspector.done().blocked:
                await record_guard_event(
                    db,
                    route=route,
                    stage="output",
                    signals=inspector.done().signals,
                    user_id=user_id,
                    role="user",
                )
                yield StreamEvent(type="blocked", content=BLOCK_MESSAGE_OUTPUT)
                return
            yield event
        else:
            yield event

    full_reply = "".join(assembled).strip()

    heuristics = inspect_output(full_reply, canary=canary)
    verdict = await judge_output(full_reply)
    signals = [
        *heuristics.signals,
        Signal("judge", verdict.complied, verdict.reason, "medium"),
    ]
    if fired_signals(signals):
        await record_guard_event(
            db,
            route=route,
            stage="output",
            signals=signals,
            user_id=user_id,
            role="user",
        )
        yield StreamEvent(type="blocked", content=BLOCK_MESSAGE_OUTPUT)
        return

    yield StreamEvent(type="done", content=full_reply)
