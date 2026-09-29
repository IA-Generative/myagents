"""Route exposing available LLM models (live list merged with a static fallback)."""

from fastapi import APIRouter

from app.llm.catalog import FALLBACK_MODELS
from app.llm.client import LlmClient, LlmUnavailableError
from app.schemas.agent import ModelProfile

router = APIRouter(prefix="/models", tags=["models"])


@router.get("", response_model=list[ModelProfile])
async def list_models():
    client = LlmClient()
    try:
        live = await client.list_models()
        if live:
            return [
                ModelProfile(id=m["id"], label=m.get("id", ""), tier="balanced")
                for m in live
            ]
    except LlmUnavailableError:
        pass
    return FALLBACK_MODELS
