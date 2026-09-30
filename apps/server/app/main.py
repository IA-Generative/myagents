"""FastAPI application entrypoint."""

import logging
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.openapi.utils import get_openapi

from app.api.routes import (
    agents,
    catalog,
    favorites,
    knowledge,
    models,
    openai_compat,
    prompt,
    ratings,
    tools,
)
from app.core.config import get_settings
from app.core.logging import setup_logging

setup_logging()
logger = logging.getLogger(__name__)

settings = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    logger.info(
        "démarrage de %s (env=%s, llm_base_url=%s, llm_default_model=%s)",
        settings.app_name,
        settings.environment,
        settings.llm_base_url,
        settings.llm_default_model,
    )
    yield
    logger.info("arrêt de %s", settings.app_name)


app = FastAPI(
    title=settings.app_name,
    lifespan=lifespan,
    swagger_ui_parameters={
        # Pré-remplit les headers dans le Swagger UI "Try it out"
        "persistAuthorization": True,
    },
)


def custom_openapi():
    """Injecte les schémas de sécurité pour le bouton 'Authorize' du Swagger UI.

    - BearerAuth : token JWT ou clé OpenWebUI (header Authorization: Bearer <token>)
    - XUserIdAuth : header X-User-ID pour le dev local (OIDC désactivé)
    """
    if app.openapi_schema:
        return app.openapi_schema
    schema = get_openapi(
        title=app.title,
        version="1.0.0",
        routes=app.routes,
    )
    schema["components"]["securitySchemes"] = {
        "BearerAuth": {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT",
            "description": (
                "Token JWT Keycloak (OIDC) ou clé OpenWebUI API. "
                "En dev (OIDC_ENABLED=false), n'importe quelle valeur est acceptée."
            ),
        },
        "XUserIdAuth": {
            "type": "apiKey",
            "in": "header",
            "name": "X-User-ID",
            "description": (
                "ID utilisateur pour le dev local (OIDC désactivé). "
                "Optionnel : si absent, utilise DEFAULT_USER_ID."
            ),
        },
    }
    # Applique les deux schémas globalement à toutes les routes.
    schema["security"] = [{"BearerAuth": []}, {"XUserIdAuth": []}]
    app.openapi_schema = schema
    return schema


app.openapi = custom_openapi

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "X-User-ID"],
)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    duration_ms = (time.perf_counter() - start) * 1000
    logger.info(
        "%s %s -> %d (%.0fms)",
        request.method,
        request.url.path,
        response.status_code,
        duration_ms,
    )
    return response


for router in (
    tools.router,
    agents.router,
    catalog.router,
    ratings.router,
    favorites.router,
    models.router,
    prompt.router,
    knowledge.router,
):
    app.include_router(router, prefix="/api")

# OpenAI-compatible surface for external callers (Open WebUI connection): no /api prefix,
# Base URL in Open WebUI is the plain OpenAI convention https://<host>/v1.
app.include_router(openai_compat.router, prefix="/v1")


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


# Serve the built Vue.js frontend as static files (must stay after /api routes).
static_path = Path(__file__).parent.parent / "static"
if static_path.exists():
    static_root = static_path.resolve()
    app.mount("/assets", StaticFiles(directory=static_path / "assets"), name="assets")

    @app.get("/{path:path}")
    async def serve_spa(path: str) -> FileResponse:
        """Catch-all serving the Vue.js SPA (client-side routing)."""
        try:
            file_path = (static_root / path).resolve()
            # is_relative_to, pas startswith : "static_evil" commence aussi par "static".
            if file_path.is_relative_to(static_root) and file_path.is_file():
                return FileResponse(file_path)
        except ValueError:
            pass
        except OSError:
            pass
        return FileResponse(static_root / "index.html")
