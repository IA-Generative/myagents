"""OpenAI-compatible /v1 endpoints exposing agents as "models" for Open WebUI.

Mounted without the /api prefix (see main.py) so the connection's Base URL in
Open WebUI is the plain OpenAI convention: https://<host>/v1.
"""

import json
import logging
import re
import time
import uuid
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, Header
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import limit_llm_openwebui, require_openwebui_key
from app.core.config import get_settings
from app.db.session import get_db
from app.llm.client import LlmClient
from app.llm.fallback import (
    LlmModelResolutionError,
    run_agent_chat_stream_with_model_fallback,
    run_agent_chat_with_model_fallback,
)
from app.schemas.agent import ChatMessage, ConfigSnapshot
from app.schemas.openai_compat import (
    OpenAIChatCompletionChoice,
    OpenAIChatCompletionRequest,
    OpenAIChatCompletionResponse,
    OpenAIModel,
    OpenAIModelList,
)
from app.services import agents as agents_service
from app.services import prompt_guard

router = APIRouter(
    tags=["openai-compat"], dependencies=[Depends(require_openwebui_key)]
)
logger = logging.getLogger(__name__)


def _llm_error_response() -> JSONResponse:
    return JSONResponse(
        status_code=502,
        content={
            "error": {
                "message": "llm_unavailable",
                "type": "api_error",
                "code": "llm_unavailable",
            }
        },
    )


def _guard_error_response(exc: prompt_guard.GuardBlockedError) -> JSONResponse:
    # Format d'erreur OpenAI : Open WebUI affiche `error.message` à l'utilisateur.
    return JSONResponse(
        status_code=422,
        content={
            "error": {
                "message": exc.message,
                "type": "invalid_request_error",
                "code": exc.code,
            }
        },
    )


_OWUI_USER_ID_RE = re.compile(r"^[A-Za-z0-9._:@-]{1,200}$")


def _audit_user_id(owui_user_id: str | None) -> str:
    """Identité pour le journal de la garde : l'utilisateur relayé par Open WebUI s'il est connu.

    L'en-tête n'est envoyé que si Open WebUI transmet l'identité
    (ENABLE_FORWARD_USER_INFO_HEADERS) ; l'appel est déjà authentifié par la clé partagée.
    """
    if owui_user_id and _OWUI_USER_ID_RE.match(owui_user_id):
        return f"openwebui:{owui_user_id}"
    return "openwebui"


def _model_not_found(model: str) -> JSONResponse:
    return JSONResponse(
        status_code=404,
        content={
            "error": {
                "message": f"model '{model}' not found",
                "type": "invalid_request_error",
                "code": "model_not_found",
            }
        },
    )


@router.get("/models", response_model=OpenAIModelList)
async def list_models(db: AsyncSession = Depends(get_db)):
    agents = await agents_service.list_exposed_agents(db)
    data = [
        OpenAIModel(
            id=str(agent.id),
            created=int(agent.created_at.timestamp()),
            name=agents_service.current_config(agent).name,
        )
        for agent in agents
    ]
    return OpenAIModelList(data=data)


async def _sse_stream_guarded(
    model: str, client: LlmClient, config: ConfigSnapshot, messages, db, route, user_id
) -> AsyncIterator[str]:
    """Real token-by-token SSE with streaming guard inspection."""
    from app.llm.sse import stream_openai_sse

    default_model = get_settings().llm_default_model
    primary_model = config.model_id or default_model

    async def run_stream(hardened: ConfigSnapshot):
        async for event in run_agent_chat_stream_with_model_fallback(
            client,
            hardened,
            history=messages,
            temperature=config.temperature,
            primary_model=primary_model,
            default_model=default_model,
        ):
            yield event

    try:
        async for sse_str in stream_openai_sse(
            prompt_guard.guarded_agent_chat_stream(
                db,
                route=route,
                user_id=user_id,
                config=config,
                history=messages,
                run=run_stream,
                skip_input_check=True,
            ),
            model,
        ):
            yield sse_str
    except prompt_guard.GuardBlockedError:
        yield _guard_error_sse(model)
    except LlmModelResolutionError:
        yield _error_sse(model, "llm_unavailable")


def _guard_error_sse(model: str) -> str:
    completion_id = f"chatcmpl-{uuid.uuid4().hex}"
    return f"data: {
        json.dumps(
            {
                'id': completion_id,
                'object': 'chat.completion.chunk',
                'created': int(time.time()),
                'model': model,
                'choices': [
                    {'index': 0, 'delta': {}, 'finish_reason': 'content_filter'}
                ],
            }
        )
    }\n\n"


def _error_sse(model: str, message: str) -> str:
    completion_id = f"chatcmpl-{uuid.uuid4().hex}"
    return f"data: {
        json.dumps(
            {
                'id': completion_id,
                'object': 'chat.completion.chunk',
                'created': int(time.time()),
                'model': model,
                'choices': [{'index': 0, 'delta': {}, 'finish_reason': 'error'}],
            }
        )
    }\n\n"


@router.post("/chat/completions", dependencies=[Depends(limit_llm_openwebui)])
async def chat_completions(
    payload: OpenAIChatCompletionRequest,
    db: AsyncSession = Depends(get_db),
    x_openwebui_user_id: str | None = Header(default=None),
):
    try:
        agent_id = uuid.UUID(payload.model)
    except ValueError:
        return _model_not_found(payload.model)

    agent = await agents_service.get_agent(db, agent_id)
    if agent is None or not agents_service.is_catalog_visible(agent):
        return _model_not_found(payload.model)

    config = agents_service.current_config(agent)
    default_model = get_settings().llm_default_model
    primary_model = config.model_id or agent.model_ref or default_model
    client = LlmClient()
    user_id = _audit_user_id(x_openwebui_user_id)

    if payload.stream:
        # Input guard must run before the stream starts: a blocked input returns
        # 422 JSON, not a 200 SSE stream.
        try:
            await prompt_guard.check_input(
                db,
                route="openai.chat_completions",
                text=prompt_guard.last_message_content(payload.messages),
                role="user",
                block_message=prompt_guard.BLOCK_MESSAGE_USER_INPUT,
                user_id=user_id,
            )
        except prompt_guard.GuardBlockedError as exc:
            return _guard_error_response(exc)

        return StreamingResponse(
            _sse_stream_guarded(
                payload.model,
                client,
                config,
                payload.messages,
                db,
                "openai.chat_completions",
                user_id,
            ),
            media_type="text/event-stream",
        )

    async def run(hardened: ConfigSnapshot) -> str:
        return await run_agent_chat_with_model_fallback(
            client,
            hardened,
            history=payload.messages,
            temperature=config.temperature,
            primary_model=primary_model,
            default_model=default_model,
        )

    try:
        reply = await prompt_guard.guarded_agent_chat(
            db,
            route="openai.chat_completions",
            user_id=user_id,
            config=config,
            history=payload.messages,
            run=run,
        )
    except prompt_guard.GuardBlockedError as exc:
        return _guard_error_response(exc)
    except LlmModelResolutionError as exc:
        logger.error(
            "chat/completions: echec LLM (agent=%s): %s", agent_id, exc.original
        )
        return _llm_error_response()

    return OpenAIChatCompletionResponse(
        id=f"chatcmpl-{uuid.uuid4().hex}",
        created=int(time.time()),
        model=payload.model,
        choices=[
            OpenAIChatCompletionChoice(
                message=ChatMessage(role="assistant", content=reply)
            )
        ],
    )
