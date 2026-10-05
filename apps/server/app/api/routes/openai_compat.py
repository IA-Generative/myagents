"""OpenAI-compatible /v1 endpoints exposing agents as "models" for Open WebUI.

Mounted without the /api prefix (see main.py) so the connection's Base URL in
Open WebUI is the plain OpenAI convention: https://<host>/v1.
"""

import json
import logging
import time
import uuid
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import limit_llm_openwebui, require_openwebui_key
from app.core.config import get_settings
from app.db.session import get_db
from app.llm import agent_runtime
from app.llm.client import LlmClient, LlmModelNotFoundError, LlmParseError, LlmUnavailableError
from app.schemas.agent import ChatMessage
from app.schemas.openai_compat import (
    OpenAIChatCompletionChoice,
    OpenAIChatCompletionRequest,
    OpenAIChatCompletionResponse,
    OpenAIModel,
    OpenAIModelList,
)
from app.services import agents as agents_service

router = APIRouter(
    tags=["openai-compat"], dependencies=[Depends(require_openwebui_key)]
)
logger = logging.getLogger(__name__)


def _llm_error_response() -> JSONResponse:
    return JSONResponse(
        status_code=502,
        content={"error": {"message": "llm_unavailable", "type": "api_error", "code": "llm_unavailable"}},
    )


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


async def _sse_full_reply(model: str, reply: str) -> AsyncIterator[str]:
    completion_id = f"chatcmpl-{uuid.uuid4().hex}"
    created = int(time.time())
    content_chunk = {
        "id": completion_id,
        "object": "chat.completion.chunk",
        "created": created,
        "model": model,
        "choices": [
            {
                "index": 0,
                "delta": {"role": "assistant", "content": reply},
                "finish_reason": None,
            }
        ],
    }
    final_chunk = {
        "id": completion_id,
        "object": "chat.completion.chunk",
        "created": created,
        "model": model,
        "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
    }
    yield f"data: {json.dumps(content_chunk)}\n\n"
    yield f"data: {json.dumps(final_chunk)}\n\n"
    yield "data: [DONE]\n\n"


@router.post("/chat/completions", dependencies=[Depends(limit_llm_openwebui)])
async def chat_completions(
    payload: OpenAIChatCompletionRequest, db: AsyncSession = Depends(get_db)
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
    try:
        reply = await agent_runtime.arun_agent_chat(
            client,
            config,
            history=payload.messages,
            model=primary_model,
            temperature=config.temperature,
        )
    except LlmModelNotFoundError as exc:
        if primary_model == default_model:
            return _llm_error_response()
        logger.warning(
            "modèle '%s' introuvable, fallback sur '%s'", primary_model, default_model
        )
        try:
            reply = await agent_runtime.arun_agent_chat(
                client,
                config,
                history=payload.messages,
                model=default_model,
                temperature=config.temperature,
            )
        except (LlmUnavailableError, LlmParseError) as exc2:
            logger.error("chat/completions: fallback LLM échoué (agent=%s): %s", agent_id, exc2)
            return _llm_error_response()
    except (LlmUnavailableError, LlmParseError) as exc:
        logger.error("chat/completions: échec LLM (agent=%s): %s", agent_id, exc)
        return _llm_error_response()

    if payload.stream:
        return StreamingResponse(
            _sse_full_reply(payload.model, reply), media_type="text/event-stream"
        )

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
