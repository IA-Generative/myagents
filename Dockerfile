# Image unique apps/server (FastAPI) + apps/web (Vue, servi en statique par FastAPI).
ARG BUN_VERSION=1.4.2
ARG PYTHON_VERSION=3.14.7
ARG UV_VERSION=0.12.20

FROM ghcr.io/astral-sh/uv:${UV_VERSION} AS uv

# ---------- Stage 1 : frontend ----------
FROM oven/bun:${BUN_VERSION}-alpine AS frontend-builder
WORKDIR /build
COPY apps/web/package.json apps/web/bun.lock ./
RUN bun install --frozen-lockfile
COPY apps/web/ ./
RUN bun run build && test -f dist/index.html

# ---------- Stage 2 : dépendances backend ----------
# WORKDIR identique au stage final : les shebangs du venv embarquent un chemin absolu.
FROM python:${PYTHON_VERSION}-slim-trixie AS backend-builder
COPY --from=uv /uv /uvx /bin/
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never
WORKDIR /app
COPY apps/server/pyproject.toml apps/server/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# ---------- Stage 3 : production ----------
FROM python:${PYTHON_VERSION}-slim-trixie AS production
# UID 10001 aligné sur le securityContext du chart helm/.
RUN useradd --system --uid 10001 --gid root --no-create-home appuser
WORKDIR /app
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

COPY --from=backend-builder /app/.venv /app/.venv
COPY apps/server/ ./
COPY --from=frontend-builder /build/dist ./static/

# Convention ADR-0004 MirAI next, alignée sur Dockerflow : l'image porte son journal en
# /app/version.json, servi sur /__version__. Les valeurs viennent de la CI (build-args :
# ci.yml pr-<n>, branches.yml beta-<sha8>, cd.yml X.Y.Z) ; un build de poste donne « dev ».
# Posé avant USER : lisible par l'utilisateur non-root, racine en lecture seule compatible.
ARG VERSION=dev
ARG COMMIT=
ARG BUILD=
ARG CODE_DATE=
ARG SOURCE=
COPY scripts/version_json.py CHANGELOG.md* /tmp/version/
RUN python /tmp/version/version_json.py --version "$VERSION" --commit "$COMMIT" --build "$BUILD" \
      --code-date "$CODE_DATE" --source "$SOURCE" --changelog /tmp/version/CHANGELOG.md \
      --out /app/version.json \
 && chmod 0644 /app/version.json \
 && rm -rf /tmp/version

USER 10001
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD ["python", "-c", "import urllib.request as u,sys; o=u.build_opener(u.ProxyHandler({})); sys.exit(0 if o.open('http://127.0.0.1:8000/api/health', timeout=4).status == 200 else 1)"]

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
