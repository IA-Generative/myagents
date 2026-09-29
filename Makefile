SHELL := /usr/bin/env bash
.DEFAULT_GOAL := help

SERVER := apps/server
WEB    := apps/web
IMAGE  ?= mes-agents:dev

.PHONY: help \
	up down restart build logs logs-server ps sh-server sh-web clean \
	migrate migration seed \
	install install-server install-web dev-server dev-web \
	check test test-server test-web lint lint-server lint-web typecheck-web format \
	image

help: ## Affiche cette aide
	@grep -E '^[a-zA-Z_%-]+:.*##' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*##"}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

# --- Docker compose (server + web + postgres + qdrant) -----------------------

up: ## Démarre tous les services (build si nécessaire)
	docker compose up -d --build

down: ## Arrête tous les services
	docker compose down

restart: ## Redémarre le backend
	docker compose restart server

build: ## (Re)construit les images de dev
	docker compose build

logs: ## Suit les logs de tous les services
	docker compose logs -f

logs-server: ## Suit les logs du backend
	docker compose logs -f server

ps: ## Liste les conteneurs et leur statut
	docker compose ps

sh-server: ## Shell dans le conteneur backend
	docker compose exec server sh

sh-web: ## Shell dans le conteneur frontend
	docker compose exec web sh

clean: ## Arrête et SUPPRIME les volumes (perte des données locales)
	docker compose down -v

# --- Base de données ---------------------------------------------------------

migrate: ## Applique les migrations Alembic
	docker compose exec server uv run alembic upgrade head

migration: ## Génère une migration Alembic (MSG="message" requis)
	@test -n "$(MSG)" || { echo 'Usage : make migration MSG="description"'; exit 1; }
	docker compose exec server uv run alembic revision --autogenerate -m "$(MSG)"

seed: ## (Re)joue le seed des agents par défaut
	docker compose exec server uv run python -m app.scripts.seed_agents

# --- Développement local (sans Docker) ---------------------------------------

install: install-server install-web ## Installe les dépendances server + web

install-server:
	cd $(SERVER) && uv sync --frozen

install-web:
	cd $(WEB) && bun install --frozen-lockfile

dev-server: ## Backend en local avec hot reload (port 8000)
	cd $(SERVER) && uv run uvicorn app.main:app --reload --port 8000

dev-web: ## Frontend en local avec hot reload (port 5173)
	cd $(WEB) && bun run dev

# --- Qualité -----------------------------------------------------------------

check: lint typecheck-web test ## Lint + typecheck + tests (équivalent CI)

test: test-server test-web ## Tests server + web

test-server: ## Tests backend (pytest)
	cd $(SERVER) && uv run pytest -q

test-web: ## Tests frontend (vitest)
	cd $(WEB) && bun run test

lint: lint-server lint-web ## Lint server + web

lint-server: ## Lint + format check backend (ruff)
	cd $(SERVER) && uv run ruff check . && uv run ruff format --check .

lint-web: ## Lint frontend (eslint)
	cd $(WEB) && bun run lint

typecheck-web: ## Typecheck frontend (vue-tsc)
	cd $(WEB) && bunx vue-tsc -b --noEmit

format: ## Formate le backend (ruff)
	cd $(SERVER) && uv run ruff check --fix . && uv run ruff format .

# --- Image de production -----------------------------------------------------

image: ## Construit l'image de production server+web (IMAGE=nom:tag)
	docker build -f Dockerfile -t $(IMAGE) .

# --- apps/next (autonome, en cours de dépréciation) --------------------------

next-%: ## Délègue à apps/next (ex. make next-up, make next-test)
	$(MAKE) -C apps/next $*
