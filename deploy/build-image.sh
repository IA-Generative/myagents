#!/usr/bin/env bash
# Build de l'image Docker MirAI Agent Builder.
# Deux images sont produites :
#   - AGENT_BUILDER_IMAGE          : stage runner (Next.js standalone, ~186 MB)
#   - AGENT_BUILDER_MIGRATOR_IMAGE : stage builder (node_modules complet + CLI
#                                    prisma, ~900 MB) utilisée par le Job K8s
#                                    `agent-builder-migrate` pour `prisma db push`.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

# shellcheck disable=SC1091
source ./deploy/prepare-env.sh

echo "Build de ${AGENT_BUILDER_IMAGE} (stage runner)"
docker build \
  --platform linux/amd64 \
  --target runner \
  -t "${AGENT_BUILDER_IMAGE}" \
  -f apps/next/Dockerfile \
  apps/next

echo "Build de ${AGENT_BUILDER_MIGRATOR_IMAGE} (stage builder — avec CLI prisma)"
docker build \
  --platform linux/amd64 \
  --target builder \
  -t "${AGENT_BUILDER_MIGRATOR_IMAGE}" \
  -f apps/next/Dockerfile \
  apps/next

echo "Build OK :"
echo "  - ${AGENT_BUILDER_IMAGE}"
echo "  - ${AGENT_BUILDER_MIGRATOR_IMAGE}"
