"""BFF endpoints backing the wizard's AI-assisted authoring features:
"Aide-moi à écrire", "Optimiser mon prompt", starter suggestions, the mandatory
anti-jailbreak validation gate, and the onboarding chat widget.

The actual LLM orchestration (prompt templating, structured output parsing)
lives in `app.llm.chains` as LangChain LCEL runnables; these routes only
validate input, invoke a chain, and map errors to HTTP responses.

Garde anti-prompt-injection (comme en production) : l'entrée est inspectée avant
tout appel LLM, et la sortie générée (heuristiques + LLM-juge) avant d'être rendue.
"""

import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user_id, limit_llm_user
from app.db.session import get_db
from app.llm import chains
from app.llm.client import LlmClient, LlmParseError, LlmUnavailableError
from app.llm.guard import BLOCK_MESSAGE_AGENT_CONFIG, BLOCK_MESSAGE_USER_INPUT
from app.schemas.agent import (
    OnboardingAgentConfig,
    OnboardingChatRequest,
    OnboardingChatResponse,
    OnboardingTurn,
    PromptAssistRequest,
    PromptResponse,
    PromptValidateRequest,
    PromptValidateResponse,
    SuggestStartersRequest,
    SuggestStartersResponse,
)
from app.services import prompt_guard

router = APIRouter(prefix="/agents", tags=["prompt"])


def _turn_text(turn: OnboardingTurn) -> str:
    """Texte complet d'un tour d'onboarding, config d'agent proposée comprise."""
    return "\n\n".join(
        [
            turn.message,
            turn.name,
            turn.description,
            turn.category,
            turn.system_prompt,
            turn.greeting,
            *turn.examples,
        ]
    )


@router.post("/prompt/assist", response_model=PromptResponse)
async def assist_prompt(
    payload: PromptAssistRequest,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(limit_llm_user),
):
    # Le prompt et les indications sont fournis par l'utilisateur.
    await prompt_guard.check_input(
        db,
        route="prompt.assist",
        text=f"{json.dumps(payload.hints, ensure_ascii=False)}\n{payload.prompt}",
        role="user",
        block_message=BLOCK_MESSAGE_AGENT_CONFIG,
        user_id=user_id,
    )
    client = LlmClient()
    try:
        generated = await chains.assist_prompt(client, payload.hints, payload.prompt)
    except LlmUnavailableError as exc:
        raise HTTPException(status_code=502, detail="llm_unavailable") from exc
    await prompt_guard.check_output(
        db, route="prompt.assist", text=generated, user_id=user_id
    )
    return PromptResponse(prompt=generated)


@router.post("/prompt/optimize", response_model=PromptResponse)
async def optimize_prompt(
    payload: PromptAssistRequest,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(limit_llm_user),
):
    if not payload.prompt.strip():
        raise HTTPException(status_code=400, detail="prompt_required")
    await prompt_guard.check_input(
        db,
        route="prompt.optimize",
        text=payload.prompt,
        role="user",
        block_message=BLOCK_MESSAGE_AGENT_CONFIG,
        user_id=user_id,
    )
    client = LlmClient()
    try:
        optimized = await chains.optimize_prompt(client, payload.prompt)
    except LlmUnavailableError as exc:
        raise HTTPException(status_code=502, detail="llm_unavailable") from exc
    await prompt_guard.check_output(
        db, route="prompt.optimize", text=optimized, user_id=user_id
    )
    return PromptResponse(prompt=optimized)


@router.post("/prompt/suggest-starters", response_model=SuggestStartersResponse)
async def suggest_starters(
    payload: SuggestStartersRequest,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(limit_llm_user),
):
    if len(payload.prompt.strip()) < 20:
        raise HTTPException(status_code=400, detail="prompt_too_short")
    # Le prompt soumis est un prompt système d'agent.
    await prompt_guard.check_input(
        db,
        route="prompt.suggest-starters",
        text=payload.prompt,
        role="system",
        block_message=BLOCK_MESSAGE_AGENT_CONFIG,
        user_id=user_id,
    )
    client = LlmClient()
    try:
        starters = await chains.suggest_starters(client, payload.prompt, payload.count)
    except LlmUnavailableError as exc:
        raise HTTPException(status_code=502, detail="llm_unavailable") from exc
    except LlmParseError as exc:
        raise HTTPException(status_code=502, detail="parse_failed") from exc
    # L'amorce et les exemples seront affichés aux utilisateurs finaux.
    await prompt_guard.check_output(
        db,
        route="prompt.suggest-starters",
        text="\n".join([starters.greeting, *starters.examples]),
        user_id=user_id,
    )
    return starters


@router.post("/prompt/validate", response_model=PromptValidateResponse)
async def validate_prompt(
    payload: PromptValidateRequest,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    if not payload.prompt.strip():
        raise HTTPException(status_code=400, detail="prompt_required")
    # Contrôle déterministe, sans appel LLM.
    await prompt_guard.check_input(
        db,
        route="prompt.validate",
        text=payload.prompt,
        role="system",
        block_message=BLOCK_MESSAGE_AGENT_CONFIG,
        user_id=user_id,
        stage="validate",
    )
    return PromptValidateResponse(ok=True)


@router.post("/onboarding-chat", response_model=OnboardingChatResponse)
async def onboarding_chat(
    payload: OnboardingChatRequest,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(limit_llm_user),
):
    if not payload.messages:
        raise HTTPException(status_code=400, detail="messages_required")
    # Le dialogue produit le prompt système qui sera publié : on bloque une
    # injection avant qu'elle ne contamine la configuration générée.
    await prompt_guard.check_input(
        db,
        route="onboarding.chat",
        text=payload.messages[-1].content,
        role="user",
        block_message=BLOCK_MESSAGE_USER_INPUT,
        user_id=user_id,
    )
    client = LlmClient()
    try:
        turn = await chains.onboarding_turn(client, payload.messages)
    except LlmUnavailableError as exc:
        raise HTTPException(status_code=502, detail="llm_unavailable") from exc
    except LlmParseError as exc:
        raise HTTPException(status_code=502, detail="parse_failed") from exc
    await prompt_guard.check_output(
        db, route="onboarding.chat", text=_turn_text(turn), user_id=user_id, role="user"
    )

    # Le LLM peut renvoyer un message vide (rare mais déjà observé) : on évite
    # d'afficher une bulle vide côté client en renvoyant un message de repli.
    if not turn.message.strip():
        turn.message = (
            "Pouvez-vous préciser votre besoin pour que je puisse vous aider ?"
        )

    agent_config = (
        OnboardingAgentConfig(
            ready=True,
            name=turn.name,
            description=turn.description,
            category=turn.category,
            system_prompt=turn.system_prompt,
            greeting=turn.greeting,
            examples=turn.examples,
        )
        if turn.ready
        else None
    )
    return OnboardingChatResponse(message=turn.message, agent_config=agent_config)
