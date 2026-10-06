"""OpenAI-compatible /v1 endpoints exposing agents as "models".

Deux appelants (contrat d'agents MirAI, docs/contrats/contrat-agents-mirai.md) :
- le socle Open WebUI, avec la clé partagée : liste des agents partagés, droits appliqués par
  ses propres fiches ;
- une personne, par son jeton Keycloak (Mon portail, Mes réunions, plug-ins) : liste et
  lancement limités à ce qu'elle a le droit de voir, usage imputé à son `sub`.

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

from app.api.deps import V1Caller, limit_v1, v1_caller
from app.core.config import get_settings
from app.db.session import get_db
from app.llm.client import LlmClient
from app.llm.fallback import LlmModelResolutionError, run_agent_chat_with_model_fallback
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

router = APIRouter(tags=["openai-compat"])
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
async def list_models(
    db: AsyncSession = Depends(get_db), caller: V1Caller = Depends(v1_caller)
):
    if caller.user is not None:
        agents = await agents_service.list_accessible(
            db, caller.user.user_id, caller.user.groups
        )
    else:
        agents = await agents_service.list_exposed_agents(db)
    data = []
    for agent in agents:
        config = agents_service.current_config(agent)
        data.append(
            OpenAIModel(
                id=str(agent.id),
                created=int(agent.created_at.timestamp()),
                name=config.name,
                info={"meta": {"description": config.description}},
            )
        )
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


@router.post("/chat/completions")
async def chat_completions(
    payload: OpenAIChatCompletionRequest,
    db: AsyncSession = Depends(get_db),
    caller: V1Caller = Depends(limit_v1),
    x_openwebui_user_id: str | None = Header(default=None),
):
    try:
        agent_id = uuid.UUID(payload.model)
    except ValueError:
        return _model_not_found(payload.model)

    agent = await agents_service.get_agent(db, agent_id)
    if agent is None:
        return _model_not_found(payload.model)
    # Un agent hors de portée répond comme un agent inexistant (contrat) : ne pas
    # confirmer l'existence d'un agent privé à un tiers.
    if caller.user is not None:
        accessible = agents_service.is_accessible(
            agent, caller.user.user_id, caller.user.groups
        )
    else:
        accessible = agents_service.is_catalog_visible(agent)
    if not accessible:
        return _model_not_found(payload.model)
    audit_user_id = (
        caller.user.user_id
        if caller.user is not None
        else _audit_user_id(x_openwebui_user_id)
    )

    config = agents_service.current_config(agent)
    default_model = get_settings().llm_default_model
    primary_model = config.model_id or agent.model_ref or default_model
    client = LlmClient()

    async def run(hardened: ConfigSnapshot) -> str:
        return await run_agent_chat_with_model_fallback(
            client,
            hardened,
            history=payload.messages,
            temperature=config.temperature,
            primary_model=primary_model,
            default_model=default_model,
        )

    # La réponse complète est contrôlée (sortie + juge) avant toute émission, y compris
    # en stream : un contenu bloqué n'est jamais envoyé, même partiellement.
    try:
        reply = await prompt_guard.guarded_agent_chat(
            db,
            route="openai.chat_completions",
            user_id=audit_user_id,
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
