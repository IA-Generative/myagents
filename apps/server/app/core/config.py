"""Application settings, loaded from environment variables (.env in dev)."""

from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _repo_root_env_file() -> str | None:
    """Locate the repo-root .env (single source of truth for local dev secrets).

    Walks up from this file looking for docker-compose.yml. Absent in the Docker
    image (only apps/server is copied there), where real env vars are used instead.
    """
    for parent in Path(__file__).resolve().parents:
        if (parent / "docker-compose.yml").exists():
            return str(parent / ".env")
    return None


_ENV_FILES = tuple(p for p in (_repo_root_env_file(), ".env") if p)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=_ENV_FILES or ".env", extra="ignore")

    app_name: str = "mes-agents-server"
    environment: str = "development"
    log_level: str = "INFO"

    database_url: str = "sqlite+aiosqlite:///./dev.db"

    @field_validator("database_url")
    @classmethod
    def _force_async_driver(cls, url: str) -> str:
        # Le secret du sous-chart helm postgres fournit "postgresql://" (driver sync non installé).
        for scheme in ("postgresql://", "postgres://"):
            if url.startswith(scheme):
                return "postgresql+asyncpg://" + url.removeprefix(scheme)
        return url

    cors_origins: list[str] = ["http://localhost:5173"]

    # Generic OpenAI-compatible LLM endpoint (OpenWebUI, Scaleway, OpenAI, Ollama...).
    llm_base_url: str = "http://localhost:11434/v1"
    llm_api_key: str = ""
    llm_default_model: str = "gpt-oss-120b"
    llm_embedding_model: str = "nomic-embed-text"

    # Shared secret authenticating inbound calls to /v1/* (Open WebUI connection). Empty disables it.
    openwebui_api_key: str = ""

    # --- SSO Keycloak / OIDC ---
    # Issuer URL (sans trailing slash). En local : http://localhost:8180/realms/myagents
    oidc_issuer: str = ""
    # Audience attendue dans le claim `aud` du token. Vide = pas de vérification d'audience.
    oidc_audience: str = "myagents-api"
    # Désactive la validation JWT en local si vide (fallback sur default_user_id).
    oidc_enabled: bool = False
    # JWKS cache TTL (seconds).
    oidc_jwks_cache_seconds: int = 300

    # Vector store used for agent knowledge bases (RAG).
    qdrant_url: str = "http://localhost:6333"

    # Placeholder identity used until real auth (Keycloak/OIDC) is wired in.
    default_user_id: str = "demo-user"


@lru_cache
def get_settings() -> Settings:
    return Settings()
