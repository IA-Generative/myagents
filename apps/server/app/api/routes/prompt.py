"""BFF endpoints backing the wizard's AI-assisted authoring features:
"Aide-moi à écrire", "Optimiser mon prompt", starter suggestions, the mandatory
anti-jailbreak validation gate, and the onboarding chat widget.

The actual LLM orchestration (prompt templating, structured output parsing)
lives in `app.llm.chains` as LangChain LCEL runnables; these routes only
validate input, invoke a chain, and map errors to HTTP responses.
"""

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import get_current_user_id
from app.llm import chains
from app.llm.client import LlmClient, LlmParseError, LlmUnavailableError
from app.llm.guard import validate_system_prompt
from app.schemas.agent import (
    OnboardingAgentConfig,
    OnboardingChatRequest,
    OnboardingChatResponse,
    PromptAssistRequest,
    PromptResponse,
    PromptValidateRequest,
    PromptValidateResponse,
    SuggestStartersRequest,
    SuggestStartersResponse,
)

router = APIRouter(prefix="/agents", tags=["prompt"])


@router.post("/prompt/assist", response_model=PromptResponse)
async def assist_prompt(
    payload: PromptAssistRequest, user_id: str = Depends(get_current_user_id)
):
    client = LlmClient()
    try:
        generated = await chains.assist_prompt(client, payload.hints, payload.prompt)
    except LlmUnavailableError as exc:
        raise HTTPException(status_code=502, detail="llm_unavailable") from exc
    return PromptResponse(prompt=generated)


@router.post("/prompt/optimize", response_model=PromptResponse)
async def optimize_prompt(
    payload: PromptAssistRequest, user_id: str = Depends(get_current_user_id)
):
    if not payload.prompt.strip():
        raise HTTPException(status_code=400, detail="prompt_required")
    client = LlmClient()
    try:
        optimized = await chains.optimize_prompt(client, payload.prompt)
    except LlmUnavailableError as exc:
        raise HTTPException(status_code=502, detail="llm_unavailable") from exc
    return PromptResponse(prompt=optimized)


@router.post("/prompt/suggest-starters", response_model=SuggestStartersResponse)
async def suggest_starters(
    payload: SuggestStartersRequest, user_id: str = Depends(get_current_user_id)
):
    if len(payload.prompt.strip()) < 20:
        raise HTTPException(status_code=400, detail="prompt_too_short")
    client = LlmClient()
    try:
        return await chains.suggest_starters(client, payload.prompt, payload.count)
    except LlmUnavailableError as exc:
        raise HTTPException(status_code=502, detail="llm_unavailable") from exc
    except LlmParseError as exc:
        raise HTTPException(status_code=502, detail="parse_failed") from exc


@router.post("/prompt/validate", response_model=PromptValidateResponse)
async def validate_prompt(
    payload: PromptValidateRequest, user_id: str = Depends(get_current_user_id)
):
    if not payload.prompt.strip():
        raise HTTPException(status_code=400, detail="prompt_required")
    blocked, reason = validate_system_prompt(payload.prompt)
    if blocked:
        raise HTTPException(status_code=422, detail=reason)
    return PromptValidateResponse(ok=True)


@router.post("/onboarding-chat", response_model=OnboardingChatResponse)
async def onboarding_chat(
    payload: OnboardingChatRequest, user_id: str = Depends(get_current_user_id)
):
    if not payload.messages:
        raise HTTPException(status_code=400, detail="messages_required")
    client = LlmClient()
    try:
        turn = await chains.onboarding_turn(client, payload.messages)
    except LlmUnavailableError as exc:
        raise HTTPException(status_code=502, detail="llm_unavailable") from exc
    except LlmParseError as exc:
        raise HTTPException(status_code=502, detail="parse_failed") from exc

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
