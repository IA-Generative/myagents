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
    model_config = SettingsConfigDict(
        env_file=_ENV_FILES or ".env", extra="ignore", hide_input_in_errors=True
    )

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
    # Délai max (secondes) d'un appel LLM (chat + embeddings) vers OpenWebUI.
    # Les modèles lourds (gpt-oss-120b) peuvent mettre >60s à répondre sous charge ;
    # 120s laisse de la marge avant de renvoyer une erreur 503 au client.
    llm_request_timeout: float = 120.0
    # Modèles des assistants d'écriture du wizard (distincts du modèle de l'agent).
    # Par défaut alignés sur llm_default_model (LLM_DEFAULT_MODEL) : surchargeables
    # via LLM_ASSIST_MODEL / LLM_ONBOARDING_MODEL si un modèle différent est voulu
    # pour le wizard. Aucune valeur en dur ailleurs dans le code.
    llm_assist_model: str | None = None
    llm_onboarding_model: str | None = None

    # Requêtes LLM par minute et par utilisateur (0 = pas de limite).
    rate_limit_per_minute: int = 30
    # Taille maximale d'un document de base de connaissances (octets).
    max_upload_bytes: int = 1_048_576
    max_knowledge_bases_per_user: int = 20
    max_documents_per_knowledge_base: int = 50

    # Shared secret authenticating inbound calls to /v1/* (Open WebUI connection). Empty disables it.
    openwebui_api_key: str = ""

    # URL publique du server vue par le navigateur (liens de téléchargement des présentations).
    public_base_url: str = "http://localhost:8000"
    # Secret de signature des liens ; vide = repli sur openwebui_api_key, et sans l'un ni l'autre
    # la génération de liens est refusée.
    presentation_link_secret: str = ""
    presentation_ttl_minutes: int = 60

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
    # Client confidentiel Keycloak : le server fait seul le flux code + PKCE (BFF), le navigateur
    # ne reçoit qu'un cookie de session.
    oidc_client_id: str = "myagents-server"
    oidc_client_secret: str = ""
    # URL du realm joignable depuis le server (ex. http://keycloak:8080/realms/myagents) ; vide =
    # oidc_issuer. L'issuer reste l'URL publique, seule vue par le navigateur.
    oidc_internal_url: str = ""
    # Origine publique du front (redirect_uri = <origine>/api/auth/callback, cookie de session).
    # Vide = https://<web_port>.<code_server_domain> derrière code-server, sinon localhost.
    web_public_url: str = ""
    web_port: int = 5173
    code_server_domain: str = ""
    # Clé de chiffrement des jetons en base ; vide = repli sur oidc_client_secret.
    session_secret: str = ""
    session_ttl_hours: int = 12

    # Vector store used for agent knowledge bases (RAG).
    qdrant_url: str = "http://localhost:6333"

    # Placeholder identity used until real auth (Keycloak/OIDC) is wired in.
    default_user_id: str = "demo-user"

    # Origines supplémentaires autorisées en `connect-src` du CSP (ex. un second IdP).
    csp_extra_connect_src: list[str] = []

    @model_validator(mode="after")
    def _default_web_public_url(self) -> Settings:
        if not self.web_public_url:
            self.web_public_url = (
                f"https://{self.web_port}.{self.code_server_domain}"
                if self.code_server_domain
                else f"http://localhost:{self.web_port}"
            )
        return self

    @model_validator(mode="after")
    def _resolve_assist_models(self) -> Settings:
        # Les modèles assist/onboarding par défaut pointent sur llm_default_model
        # (LLM_DEFAULT_MODEL) tant qu'ils ne sont pas surchargés explicitement.
        if self.llm_assist_model is None:
            self.llm_assist_model = self.llm_default_model
        if self.llm_onboarding_model is None:
            self.llm_onboarding_model = self.llm_default_model
        return self

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

    @property
    def cookie_secure(self) -> bool:
        return self.web_public_url.startswith("https://")


@lru_cache
def get_settings() -> Settings:
    return Settings()
