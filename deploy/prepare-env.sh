#!/usr/bin/env bash
# Charge et valide la configuration de déploiement.
#
# Stratégie en cascade (première valeur rencontrée gagne) :
#   1. Variables déjà exportées dans le shell (CI, override ponctuel)
#   2. ./.env                       (overrides spécifiques à Agent Builder)
#   3. ../owuicore-main/.env        (credentials et config partagés du socle)
#
# Résultat : on ne ressaisit JAMAIS les credentials Scaleway / Registry /
# Keycloak dans ce repo. Ils restent dans le .env du socle, source unique
# de vérité.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

# shellcheck disable=SC1091
source "${ROOT_DIR}/deploy/scripts/load_env.sh"

# 1. shell env est déjà en place (rien à faire — load_dotenv_preserve_existing
#    respecte les variables existantes).

# 2. .env local (overrides Agent Builder)
if [[ -f .env ]]; then
  load_dotenv_preserve_existing .env
fi

# 3. .env du socle owuicore-main (credentials partagés)
SOCLE_ENV="${OWUICORE_ENV_FILE:-${ROOT_DIR}/../owuicore-main/.env}"
if [[ -f "$SOCLE_ENV" ]]; then
  echo "Chargement du .env du socle : ${SOCLE_ENV}"
  load_dotenv_preserve_existing "$SOCLE_ENV"
else
  echo "Note : ${SOCLE_ENV} introuvable — déploiement isolé, tout doit être dans ./.env" >&2
fi

# --- Valeurs par défaut et dérivées ---
: "${NAMESPACE:=miraiku}"
export NAMESPACE

# L'image Agent Builder est propre à ce repo ; si elle n'est pas définie,
# on la dérive du REGISTRY du socle et d'un IMAGE_TAG.
: "${IMAGE_TAG:=dev}"
if [[ -z "${AGENT_BUILDER_IMAGE:-}" && -n "${REGISTRY:-}" ]]; then
  export AGENT_BUILDER_IMAGE="${REGISTRY}/miraiku-agents:${IMAGE_TAG}"
fi
# Image migrator = stage `builder` avec le CLI prisma, pour le Job K8s
# `agent-builder-migrate`. Par défaut, dérivée du registry + tag, avec un
# suffixe -migrator.
if [[ -z "${AGENT_BUILDER_MIGRATOR_IMAGE:-}" ]]; then
  if [[ -n "${REGISTRY:-}" ]]; then
    export AGENT_BUILDER_MIGRATOR_IMAGE="${REGISTRY}/miraiku-agents-migrator:${IMAGE_TAG}"
  else
    # Fallback local (docker-compose sans push)
    export AGENT_BUILDER_MIGRATOR_IMAGE="miraiku-agents:migrator"
  fi
fi

# URL OpenWebUI par défaut : service K8s interne
: "${OWUI_BASE_URL:=http://openwebui:80}"
export OWUI_BASE_URL

# Issuer Keycloak dérivé de KEYCLOAK_HOST si présent dans le .env du socle
if [[ -z "${KEYCLOAK_ISSUER:-}" && -n "${KEYCLOAK_HOST:-}" ]]; then
  export KEYCLOAK_ISSUER="https://${KEYCLOAK_HOST}/realms/${KEYCLOAK_REALM:-openwebui}"
fi

: "${KEYCLOAK_CLIENT_ID:=miraiku-agents}"
export KEYCLOAK_CLIENT_ID

: "${AGENTS_HOST:=myagents.fake-domain.name}"
: "${AGENTS_TLS_SECRET_NAME:=agent-builder-tls}"
export AGENTS_HOST AGENTS_TLS_SECRET_NAME

# Scaleway Generative APIs (LLM). Le modèle par défaut est aligné sur celui
# du socle (DEFAULT_MODELS=gpt-oss-120b dans deployment-openwebui.yaml).
: "${SCW_LLM_MODEL:=gpt-oss-120b}"
export SCW_LLM_BASE_URL SCW_LLM_MODEL

# --- Validation ---
required_vars=(
  NAMESPACE
  AGENT_BUILDER_IMAGE
  AGENT_BUILDER_MIGRATOR_IMAGE
  AGENTS_HOST
  AGENTS_TLS_SECRET_NAME
  LETSENCRYPT_EMAIL
  OWUI_BASE_URL
  KEYCLOAK_ISSUER
  KEYCLOAK_CLIENT_SECRET
  NEXTAUTH_SECRET
  DATABASE_URL
)

missing=0
for var in "${required_vars[@]}"; do
  if [[ -z "${!var:-}" ]]; then
    echo "Variable manquante : ${var}" >&2
    missing=1
  fi
done

if [[ "$missing" -ne 0 ]]; then
  echo "" >&2
  echo "Astuce : vérifiez que ../owuicore-main/.env est rempli et que .env" >&2
  echo "contient au moins AGENT_BUILDER_IMAGE, KEYCLOAK_CLIENT_SECRET," >&2
  echo "NEXTAUTH_SECRET et DATABASE_URL." >&2
  exit 1
fi

echo "Environnement OK (namespace=${NAMESPACE}, host=${AGENTS_HOST}, image=${AGENT_BUILDER_IMAGE})"
