#!/usr/bin/env bash
# Monte (ou met à jour) la preview bêta de l'ancienne pile Next.js :
#   https://myagents-nextjs.beta-preview.numerique-interieur.com
# Usage : deploy/k8s/preview-beta/deploy.sh <étiquette d'image>   (ex. nextjs-preview-a67d2c2)
# Les images <registre>/myagents:<étiquette> et :<étiquette>-migrator doivent être poussées
# (docker build --platform linux/amd64 --target runner|builder).
# Retrait : kubectl delete ns preview-myagents-nextjs
set -euo pipefail
cd "$(dirname "$0")"
TAG="${1:?usage: deploy.sh <tag>}"
REGISTRE=rg.fr-par.scw.cloud/funcscwnspricelessmontalcinhiacgnzi/myagents
NS=preview-myagents-nextjs

sed "s#IMAGE_RUNNER#${REGISTRE}:${TAG}#" manifests.yaml | kubectl apply -f -

# Secrets : créés une seule fois, jamais régénérés (la base garde son mot de passe).
if ! kubectl -n "$NS" get secret agent-builder-postgres >/dev/null 2>&1; then
  PG=$(openssl rand -hex 24)
  kubectl -n "$NS" create secret generic agent-builder-postgres --from-literal=password="$PG"
  kubectl -n "$NS" create secret generic agent-builder-secrets \
    --from-literal=DATABASE_URL="postgresql://app:${PG}@postgres:5432/agentbuilder?schema=public" \
    --from-literal=NEXTAUTH_SECRET="$(openssl rand -hex 32)"
fi
# Tirage depuis le registre Scaleway : même secret que l'ancien namespace myagents.
if ! kubectl -n "$NS" get secret scw-registry-pull >/dev/null 2>&1; then
  kubectl -n myagents get secret scw-registry-pull -o json \
    | jq 'del(.metadata.namespace,.metadata.uid,.metadata.resourceVersion,.metadata.creationTimestamp,.metadata.annotations,.metadata.ownerReferences)' \
    | kubectl -n "$NS" apply -f -
fi

kubectl -n "$NS" rollout status statefulset/postgres --timeout=180s
kubectl -n "$NS" delete job agent-builder-migrate --ignore-not-found
sed "s#IMAGE_MIGRATOR#${REGISTRE}:${TAG}-migrator#" job-migrate.yaml | kubectl apply -f -
kubectl -n "$NS" wait --for=condition=complete job/agent-builder-migrate --timeout=300s
kubectl -n "$NS" rollout restart deploy/agent-builder
kubectl -n "$NS" rollout status deploy/agent-builder --timeout=300s
