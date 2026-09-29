#!/usr/bin/env bash
# Déploie MirAI Agent Builder sur le cluster K8s Scaleway.
# Orchestration calquée sur owuicore-main/deploy/deploy-k8s.sh.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

# shellcheck disable=SC1091
source ./deploy/prepare-env.sh

: "${DEPLOYMENT_WAIT_TIMEOUT_SECONDS:=600}"
export DEPLOYMENT_WAIT_TIMEOUT_SECONDS

for dep in kubectl docker envsubst curl; do
  if ! command -v "$dep" >/dev/null 2>&1; then
    echo "Dépendance manquante : $dep" >&2
    exit 1
  fi
done

# 1. Build + push
./deploy/build-image.sh
./deploy/push-image.sh

# 2. Secrets
./deploy/prepare-registry-secret.sh || true
./deploy/prepare-secrets.sh

# 3. Rendu des manifestes par envsubst
mkdir -p deploy/k8s/rendered
RENDER_VARS='${NAMESPACE} ${AGENT_BUILDER_IMAGE} ${AGENT_BUILDER_MIGRATOR_IMAGE} ${AGENTS_HOST} ${AGENTS_TLS_SECRET_NAME} ${OWUI_BASE_URL} ${KEYCLOAK_ISSUER} ${SCW_LLM_BASE_URL} ${SCW_LLM_MODEL} ${OPENWEBUI_HOST}'

for manifest in deploy/k8s/base/*.yaml; do
  name="$(basename "$manifest")"
  [[ "$name" == "secret.example.yaml" ]] && continue
  [[ "$name" == "kustomization.yaml" ]] && continue
  envsubst "$RENDER_VARS" < "$manifest" > "deploy/k8s/rendered/$name"
done

# 4. Application
echo "Application du namespace..."
kubectl apply -f deploy/k8s/rendered/namespace.yaml

echo "Application de la configmap..."
kubectl apply -f deploy/k8s/rendered/configmap.yaml

# 5. Migration DB — on relance le Job à chaque déploiement
echo "Lancement du Job de migration Prisma..."
kubectl -n "$NAMESPACE" delete job agent-builder-migrate --ignore-not-found
kubectl apply -f deploy/k8s/rendered/job-migrate.yaml
kubectl -n "$NAMESPACE" wait --for=condition=complete \
  job/agent-builder-migrate --timeout="${DEPLOYMENT_WAIT_TIMEOUT_SECONDS}s" \
  || { kubectl -n "$NAMESPACE" logs job/agent-builder-migrate; exit 1; }

# 6. App workloads
echo "Application du Deployment / Service / Ingress..."
kubectl apply -f deploy/k8s/rendered/deployment.yaml
kubectl apply -f deploy/k8s/rendered/service.yaml
kubectl apply -f deploy/k8s/rendered/ingress.yaml

# 7. Force un rollout même si le template n'a pas changé — nécessaire quand
#    on redéploie la même balise avec un nouveau digest, sinon kubectl apply
#    ne crée pas de nouveau ReplicaSet et les vieux pods continuent à tourner.
kubectl -n "$NAMESPACE" rollout restart deployment/agent-builder

# 8. Attente rollout
kubectl -n "$NAMESPACE" rollout status deployment/agent-builder \
  --timeout="${DEPLOYMENT_WAIT_TIMEOUT_SECONDS}s"

echo ""
echo "=== Déploiement MirAI Agent Builder terminé ==="
kubectl -n "$NAMESPACE" get pods,svc,ingress -l app=agent-builder
echo ""
echo "URL : https://${AGENTS_HOST}"
