#!/usr/bin/env bash
# Crée/met à jour le Secret docker-registry `owui-registry` dans le namespace
# cible, pour que le kubelet puisse puller l'image depuis Scaleway Container
# Registry. Même nom et même pattern que
# owuicore-main/deploy/prepare-registry-secrets.sh.
#
# Si NAMESPACE == celui du socle (`miraiku`), le secret existe probablement
# déjà (déployé par le socle) : kubectl apply est idempotent donc on le
# met simplement à jour.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

# shellcheck disable=SC1091
source ./deploy/prepare-env.sh

if [[ -z "${REGISTRY_SERVER:-}" || -z "${REGISTRY_USERNAME:-}" || -z "${REGISTRY_PASSWORD:-}" ]]; then
  echo "Registry credentials incomplets — skip (l'image doit déjà être accessible)"
  exit 0
fi

if [[ "${REGISTRY_USERNAME}" == "CHANGE_ME" || "${REGISTRY_PASSWORD}" == "CHANGE_ME" ]]; then
  echo "Registry credentials encore à CHANGE_ME — skip"
  exit 0
fi

kubectl get namespace "$NAMESPACE" >/dev/null 2>&1 || kubectl create namespace "$NAMESPACE"

kubectl -n "$NAMESPACE" create secret docker-registry owui-registry \
  --docker-server="${REGISTRY_SERVER}" \
  --docker-username="${REGISTRY_USERNAME}" \
  --docker-password="${REGISTRY_PASSWORD}" \
  --docker-email="${REGISTRY_EMAIL:-ops@example.local}" \
  --dry-run=client -o yaml | kubectl apply -f -

echo "Secret owui-registry appliqué dans ${NAMESPACE}"
