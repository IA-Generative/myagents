#!/usr/bin/env bash
# Push de l'image Agent Builder vers Scaleway Container Registry.
# Utilise les variables REGISTRY_SERVER / REGISTRY_USERNAME / REGISTRY_PASSWORD
# héritées de owuicore-main/.env (même convention que le socle).
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

# shellcheck disable=SC1091
source ./deploy/prepare-env.sh

: "${REGISTRY_SERVER:?REGISTRY_SERVER is required (hérité de owuicore-main/.env)}"
: "${REGISTRY_USERNAME:?REGISTRY_USERNAME is required}"
: "${REGISTRY_PASSWORD:?REGISTRY_PASSWORD is required}"
: "${AGENT_BUILDER_IMAGE:?AGENT_BUILDER_IMAGE is required}"
: "${AGENT_BUILDER_MIGRATOR_IMAGE:?AGENT_BUILDER_MIGRATOR_IMAGE is required}"

echo "Logging in to ${REGISTRY_SERVER}..."
echo "${REGISTRY_PASSWORD}" | docker login "${REGISTRY_SERVER}" \
  -u "${REGISTRY_USERNAME}" --password-stdin

echo "Pushing ${AGENT_BUILDER_IMAGE}..."
docker push "${AGENT_BUILDER_IMAGE}"

echo "Pushing ${AGENT_BUILDER_MIGRATOR_IMAGE}..."
docker push "${AGENT_BUILDER_MIGRATOR_IMAGE}"

echo "Push OK"
