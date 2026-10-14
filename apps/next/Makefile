SHELL := /usr/bin/env bash
.DEFAULT_GOAL := help

.PHONY: help install dev build lint typecheck test up down logs docker-build k8s-deploy k8s-logs

help: ## Affiche cette aide
	@grep -E '^[a-zA-Z_-]+:.*##' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*##"}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

install: ## Installe les dépendances (bun)
	bun install --frozen-lockfile

dev: ## Serveur Next.js en mode dev (port 3001)
	bun run dev

build: ## Build production (prisma generate + next build)
	bun run build

lint: ## ESLint
	bun run lint

typecheck: ## tsc --noEmit
	bun run typecheck

test: ## Vitest
	bun run test

up: ## Démarre postgres + migration + app (docker compose)
	docker compose up -d --build

down: ## Arrête les services
	docker compose down

logs: ## Suit les logs
	docker compose logs -f

docker-build: ## Build des images runner + migrator
	./deploy/build-image.sh

k8s-deploy: ## Déploiement complet sur K8s Scaleway
	./deploy/deploy-k8s.sh

k8s-logs: ## Logs du Deployment
	kubectl -n $${NAMESPACE:-miraiku} logs deploy/agent-builder --tail=100 -f
