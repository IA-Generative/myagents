# Image de dev (hot reload) — l'image de production est le Dockerfile racine.
ARG PYTHON_VERSION=3.14.7
ARG UV_VERSION=0.12.20

FROM ghcr.io/astral-sh/uv:${UV_VERSION} AS uv

FROM python:${PYTHON_VERSION}-slim-trixie
COPY --from=uv /uv /uvx /bin/
# Venv hors de /app : le montage du code source en compose ne doit pas le masquer.
ENV UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/opt/venv

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project

COPY . .
RUN uv sync --frozen

EXPOSE 8000
CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
