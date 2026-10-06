"""FastAPI application entrypoint."""

import logging
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes import (
    agents,
    auth,
    catalog,
    favorites,
    knowledge,
    models,
    openai_compat,
    presentations,
    prompt,
    ratings,
    tools,
)
from app.core.config import get_settings
from app.core.csp import CSP_EXEMPT_PATHS, build_csp
from app.core.logging import setup_logging
from app.services.prompt_guard import GuardBlockedError
from app.version import VERSION_PATH
from app.version import router as version_router

setup_logging()
logger = logging.getLogger(__name__)

settings = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    logger.info(
        "démarrage de %s (env=%s, openai_base_url=%s, llm_default_model=%s)",
        settings.app_name,
        settings.environment,
        settings.openai_base_url,
        settings.llm_default_model,
    )
    yield
    logger.info("arrêt de %s", settings.app_name)


app = FastAPI(
    title=settings.app_name,
    lifespan=lifespan,
    # Pas de documentation interactive en production.
    docs_url=None if settings.is_production else "/docs",
    redoc_url=None if settings.is_production else "/redoc",
    openapi_url=None if settings.is_production else "/openapi.json",
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
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-User-ID"],
)

_SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
}
_CSP = build_csp(settings)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    for name, value in _SECURITY_HEADERS.items():
        response.headers.setdefault(name, value)
    if request.url.path not in CSP_EXEMPT_PATHS:
        response.headers.setdefault("Content-Security-Policy", _CSP)
    if settings.is_production:
        response.headers.setdefault(
            "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
        )
    return response


@app.exception_handler(GuardBlockedError)
async def guard_blocked(_: Request, exc: GuardBlockedError) -> JSONResponse:
    """Refus de la garde : code stable (`error`) + message sobre en français.

    `detail` reprend le message pour le front, qui affiche ce champ.
    """
    return JSONResponse(
        status_code=422,
        content={"error": exc.code, "message": exc.message, "detail": exc.message},
    )


@app.middleware("http")
async def log_requests(request: Request, call_next):
    # /__version__ est lu en boucle par le noteur de version : hors journal (ADR-0004).
    if request.url.path == VERSION_PATH:
        return await call_next(request)
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
    auth.router,
    agents.router,
    catalog.router,
    ratings.router,
    favorites.router,
    models.router,
    prompt.router,
    knowledge.router,
    presentations.router,
):
    app.include_router(router, prefix="/api")

# Liens de navigation hors /api (déconnexion du menu commun) : avant le catch-all de la SPA.
app.include_router(auth.racine)

# OpenAI-compatible surface for external callers (Open WebUI connection): no /api prefix,
# Base URL in Open WebUI is the plain OpenAI convention https://<host>/v1.
app.include_router(openai_compat.router, prefix="/v1")


# Version de l'image (ADR-0004) : publique, avant le catch-all de la SPA qui rendrait sinon
# index.html en 200 sur /__version__.
app.include_router(version_router)


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
        if path.split("/", 1)[0] in {"api", "v1"}:
            raise HTTPException(status_code=404, detail="not_found")
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
