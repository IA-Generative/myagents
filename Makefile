SHELL := /usr/bin/env bash
.DEFAULT_GOAL := help

SERVER := apps/server
WEB    := apps/web
IMAGE  ?= mes-agents:dev

.PHONY: help \
	up up-owui up-sso down restart build logs logs-server logs-owui logs-terminal logs-keycloak ps sh-server sh-web clean \
	ensure-env bootstrap reset \
	migrate migration seed \
	install install-server install-web dev-server dev-web \
	check test test-server test-web lint lint-server lint-web typecheck-web format \
	image

help: ## Affiche cette aide
	@grep -E '^[a-zA-Z_%-]+:.*##' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*##"}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

# --- Docker compose (server + web + postgres + qdrant) -----------------------

up: ## Démarre tous les services (build si nécessaire)
	docker compose up -d --build

up-owui: ensure-env ## Démarre la stack + OpenWebUI local (http://localhost:3000)
	@grep -qE '^OPENWEBUI_API_KEY=.+' .env 2>/dev/null || { echo 'OPENWEBUI_API_KEY manquant dans .env (openssl rand -hex 32)'; exit 1; }
	docker compose --profile owui up -d --build

up-sso: ensure-env ## Démarre la stack + Keycloak + OpenWebUI (SSO complet)
	@grep -qE '^OPENWEBUI_API_KEY=.+' .env 2>/dev/null || { echo 'OPENWEBUI_API_KEY manquant dans .env (openssl rand -hex 32)'; exit 1; }
	docker compose --profile sso --profile owui up -d --build

down: ## Arrête tous les services (OpenWebUI + Keycloak inclus)
	docker compose --profile owui --profile sso down

restart: ## Redémarre le backend
	docker compose restart server

build: ## (Re)construit les images de dev
	docker compose build

logs: ## Suit les logs de tous les services
	docker compose logs -f

logs-server: ## Suit les logs du backend
	docker compose logs -f server

logs-owui: ## Suit les logs d'OpenWebUI
	docker compose logs -f openwebui

logs-terminal: ## Suit les logs d'Open Terminal
	docker compose logs -f open-terminal

logs-keycloak: ## Suit les logs de Keycloak
	docker compose logs -f keycloak

ps: ## Liste les conteneurs et leur statut
	docker compose ps

sh-server: ## Shell dans le conteneur backend
	docker compose exec server sh

sh-web: ## Shell dans le conteneur frontend
	docker compose exec web sh

clean: ## Arrête et SUPPRIME les volumes (perte des données locales)
	docker compose --profile owui --profile sso down -v

# --- Environnement complet depuis zéro ---------------------------------------

ensure-env: # Crée .env et génère les clés et mots de passe de dev absents (idempotent)
	@test -f .env || cp .env.example .env
	@for k in OPENWEBUI_API_KEY OPENWEBUI_WEBUI_SECRET_KEY OPEN_TERMINAL_API_KEY KEYCLOAK_ADMIN_PASSWORD KEYCLOAK_DEV_ADMIN_PASSWORD KEYCLOAK_DEV_USER_PASSWORD; do \
		grep -qE "^$$k=.+" .env || { sed -i -E "/^#? ?$$k=/d" .env; echo "$$k=$$(openssl rand -hex 32)" >> .env; echo "$$k généré dans .env"; }; \
	done

bootstrap: ensure-env up-sso migrate seed ## Projet complet : .env, stack + Keycloak + OpenWebUI, migrations, seed
	@p() { v=$$(grep -E "^$$1=" .env | tail -1 | cut -d= -f2); echo "$${v:-$$2}"; }; \
	echo "web http://localhost:$$(p WEB_PORT 5173) | api http://localhost:$$(p SERVER_PORT 8000)/docs | openwebui http://localhost:$$(p OPENWEBUI_PORT 3000) | keycloak http://localhost:$$(p KEYCLOAK_PORT 8180)"

reset: clean bootstrap ## SUPPRIME les volumes puis reconstruit tout depuis zéro

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
