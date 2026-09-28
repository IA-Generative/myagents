SHELL := /usr/bin/env bash

.PHONY: help install dev build lint typecheck test docker-build docker-up docker-down k8s-deploy k8s-logs

help:
	@echo "Cibles disponibles :"
	@echo "  install        npm ci"
	@echo "  dev            Lance le serveur Next.js en mode dev (port 3001)"
	@echo "  build          Build production (prisma generate + next build)"
	@echo "  lint           eslint"
	@echo "  typecheck      tsc --noEmit"
	@echo "  test           vitest run"
	@echo "  docker-build   Build de l'image via deploy/build-image.sh"
	@echo "  docker-up      docker compose up -d --build"
	@echo "  docker-down    docker compose down"
	@echo "  k8s-deploy     Déploiement complet sur K8s Scaleway"
	@echo "  k8s-logs       Logs du Deployment"

install:
	cd apps/next && bun install

dev:
	cd apps/next && bun run dev

build:
	cd apps/next && bun run build

lint:
	cd apps/next && bun run lint

typecheck:
	cd apps/next && bun run typecheck

test:
	cd apps/next && bun run test

docker-build:
	./deploy/build-image.sh

docker-up:
	docker compose up -d --build

docker-down:
	docker compose down

k8s-deploy:
	./deploy/deploy-k8s.sh

k8s-logs:
	kubectl -n $${NAMESPACE:-miraiku} logs deploy/agent-builder --tail=100 -f
