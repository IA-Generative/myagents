#!/usr/bin/env bash
# Crée/met à jour le Secret K8s `agent-builder-secrets`.
# Pattern identique à owuicore-main/deploy/prepare-k8s-secrets.sh :
# kubectl create secret generic --from-literal=... --dry-run | kubectl apply.
# Aucun yaml rendu sur disque, les valeurs ne transitent pas par un fichier.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

# shellcheck disable=SC1091
source ./deploy/prepare-env.sh

kubectl get namespace "$NAMESPACE" >/dev/null 2>&1 || kubectl create namespace "$NAMESPACE"

declare -a literals=(
  "--from-literal=NEXTAUTH_SECRET=${NEXTAUTH_SECRET}"
  "--from-literal=KEYCLOAK_CLIENT_SECRET=${KEYCLOAK_CLIENT_SECRET}"
  "--from-literal=DATABASE_URL=${DATABASE_URL}"
)
# OWUI_ADMIN_API_KEY est optionnel : sans lui, la création d'agent côté
# OpenWebUI est skip silencieusement (l'agent n'existe qu'en base locale).
if [[ -n "${OWUI_ADMIN_API_KEY:-}" ]]; then
  literals+=("--from-literal=OWUI_ADMIN_API_KEY=${OWUI_ADMIN_API_KEY}")
fi

kubectl -n "$NAMESPACE" create secret generic agent-builder-secrets \
  "${literals[@]}" \
  --dry-run=client -o yaml | kubectl apply -f -

echo "Secret agent-builder-secrets appliqué dans ${NAMESPACE}"
