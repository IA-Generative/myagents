"""Application settings, loaded from environment variables (.env in dev)."""

from functools import lru_cache
from pathlib import Path

from pydantic import field_validator, model_validator
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
    openai_base_url: str = "http://localhost:11434/v1"
    openai_api_key: str = ""
    llm_default_model: str = "gpt-oss-120b"
    llm_embedding_model: str = "nomic-embed-text"
    # Modèles des assistants d'écriture du wizard (distincts du modèle de l'agent).
    llm_assist_model: str = "gpt-oss-120b"
    llm_onboarding_model: str = "mistral-small-3.2-24b-instruct-2506"

    # Requêtes LLM par minute et par utilisateur (0 = pas de limite).
    rate_limit_per_minute: int = 30
    # Taille maximale d'un document de base de connaissances (octets).
    max_upload_bytes: int = 1_048_576
    max_knowledge_bases_per_user: int = 20
    max_documents_per_knowledge_base: int = 50

    # Shared secret authenticating inbound calls to /v1/* (Open WebUI connection). Empty disables it.
    openwebui_api_key: str = ""

    # --- SSO Keycloak / OIDC ---
    # Issuer URL (sans trailing slash). En local : http://localhost:8180/realms/myagents
    oidc_issuer: str = ""
    # Audience attendue dans le claim `aud` du token. Vide = pas de vérification d'audience.
    oidc_audience: str = "myagents-api"
    # Désactive la validation JWT en local si vide (fallback sur default_user_id).
    oidc_enabled: bool = False
    # URL JWKS explicite (ex. adresse interne du cluster) ; défaut : dérivée de l'issuer.
    oidc_jwks_url: str = ""
    # JWKS cache TTL (seconds).
    oidc_jwks_cache_seconds: int = 300

    # Vector store used for agent knowledge bases (RAG).
    qdrant_url: str = "http://localhost:6333"

    # Placeholder identity used until real auth (Keycloak/OIDC) is wired in.
    default_user_id: str = "demo-user"

    # Origines supplémentaires autorisées en `connect-src` du CSP (ex. un second IdP).
    csp_extra_connect_src: list[str] = []

    @model_validator(mode="after")
    def _require_auth_in_production(self) -> Settings:
        if self.oidc_enabled and not self.oidc_issuer:
            raise ValueError("OIDC_ISSUER est requis quand OIDC_ENABLED=true")
        if self.environment.lower() in {"production", "prod"} and not self.oidc_enabled:
            raise ValueError("OIDC_ENABLED=true est obligatoire en production")
        return self

    @property
    def is_production(self) -> bool:
        return self.environment.lower() in {"production", "prod"}


@lru_cache
def get_settings() -> Settings:
    return Settings()
