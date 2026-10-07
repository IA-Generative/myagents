"""Generic OpenAI-compatible LLM client (works with OpenWebUI, Scaleway, OpenAI, Ollama...).

This module only owns endpoint/model configuration and the static model list.
All agentic behaviour (prompt templating, chat history, structured output) lives
in `app.llm.chains`, built as LangChain LCEL runnables (`prompt | model | parser`)
on top of the `ChatOpenAI` instances handed out by `LlmClient.chat_model`.
"""

import logging

import httpx
from langchain_openai import ChatOpenAI, OpenAIEmbeddings

from app.core.config import get_settings

logger = logging.getLogger(__name__)


class LlmUnavailableError(RuntimeError):
    """The LLM endpoint could not be reached or returned an error."""


class LlmParseError(RuntimeError):
    """The LLM replied but its output didn't match the expected structured schema."""


class LlmModelNotFoundError(LlmUnavailableError):
    """The LLM endpoint rejected the request because the model name is unknown."""


class LlmClient:
    def __init__(self, base_url: str | None = None, api_key: str | None = None) -> None:
        settings = get_settings()
        self.base_url = (base_url or settings.openai_base_url).rstrip("/")
        # Most self-hosted OpenAI-compatible servers (Ollama, OpenWebUI...) ignore the
        # key but the OpenAI SDK requires a non-empty value.
        self.api_key = api_key or settings.openai_api_key or "not-needed"
        self.timeout = settings.llm_request_timeout

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def chat_model(self, model: str, temperature: float = 0.7) -> ChatOpenAI:
        """LangChain chat model bound to this client's endpoint, ready to compose in a chain."""
        logger.debug(
            "création d'un ChatOpenAI (base_url=%s model=%s temperature=%s)",
            self.base_url,
            model,
            temperature,
        )
        return ChatOpenAI(
            base_url=self.base_url,
            api_key=self.api_key,
            model=model,
            temperature=temperature,
            timeout=self.timeout,
            max_retries=2,
        )

    def embeddings(self, model: str | None = None) -> OpenAIEmbeddings:
        """LangChain embeddings model bound to this client's endpoint, for RAG ingestion/retrieval."""
        settings = get_settings()
        return OpenAIEmbeddings(
            base_url=self.base_url,
            api_key=self.api_key,
            model=model or settings.llm_embedding_model,
            timeout=self.timeout,
            check_embedding_ctx_length=False,
        )

    async def list_models(self) -> list[dict]:
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                res = await client.get(
                    f"{self.base_url}/models", headers=self._headers()
                )
                res.raise_for_status()
                data = res.json().get("data", [])
                logger.info(
                    "list_models: %d modèle(s) disponible(s) sur %s",
                    len(data),
                    self.base_url,
                )
                return data
        except httpx.HTTPError as exc:
            logger.error("list_models: endpoint %s injoignable: %s", self.base_url, exc)
            raise LlmUnavailableError(str(exc)) from exc
