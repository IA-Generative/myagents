# Helm Chart Deployment Guide

Ce répertoire contient le chart Helm pour déployer `myagents` sur Kubernetes via ArgoCD.

## Prérequis de sécurité

- **SSO obligatoire** : avec `ENVIRONMENT=production` (défaut du chart), le server refuse de
  démarrer sans `OIDC_ENABLED=true` et `OIDC_ISSUER`. Renseigner `app.env.OIDC_ISSUER` (claim `iss`
  exact des tokens) et, si besoin, `OIDC_JWKS_URL` (adresse interne du cluster).
- **Secrets** : `OPENAI_API_KEY` et `OPENWEBUI_API_KEY` (sans elle, `/v1/*` répond 401) via
  `app.envSecret` ou un secret externe.
- **Migrations** : un Job Helm (`post-install`/`post-upgrade`) joue `alembic upgrade head`
  (désactivable via `app.migrations.enabled`). Sous ArgoCD, il s'exécute en `PostSync`.

## Structure des fichiers values

- **`values.yaml`** : Configuration de base, portée par défaut
- **`values-beta.yaml`** : Surcharges pour l'environnement de développement/local
- **`values-preview.yaml`** : Surcharges pour l'environnement preview (PR)
- **`values-prod.yaml`** : Surcharges pour la production

## Secrets Vault (VaultStaticSecret Operator)

Les secrets sensibles (`LLM_API_KEY`, `OPENWEBUI_API_KEY`) sont synchronisés depuis Vault via Vault Secrets Operator. Le chemin Vault est spécifique à chaque environnement :

| Environnement | Path Vault |
|---------------|------------|
| preview | `myagents/preview/app` |
| beta | `myagents/beta/app` |
| prod | `myagents/prod/app` |

Le Vault Secrets Operator crée automatiquement un Secret Kubernetes `myagents-secrets` à partir de ces chemins et déclenche un rollout du Deployment.

Configuration requise dans le cluster :
- Vault Secrets Operator installé et configuré
- CRD `VaultStaticSecret` nommé `vault-auth` pointant vers le mount KV (`kv`)
- Policy Vault autorisant la lecture sur `myagents/<env>/app`

```yaml
apiVersion: secrets.hashicorp.com/v1beta1
kind: VaultStaticSecret
metadata:
  name: myagents-secrets
spec:
  mount: kv
  path: myagents/preview/app
  type: kv-v2
  vaultAuthRef: vault-auth
  destination:
    create: true
    name: myagents-secrets
    type: Opaque
    rolloutRestartTargets:
      - kind: Deployment
        name: mes-agents
```

## Déploiement avec ArgoCD

### 1. Application ArgoCD - environnement beta (preprod)

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: myagents-beta
  namespace: argocd
spec:
  project: default
  source:
    repoURL: https://github.com/ia-generative/myagents
    targetRevision: main
    path: helm/
    helm:
      valuesFiles:
        - values.yaml
        - values-beta.yaml
  destination:
    server: https://kubernetes.default.svc
    namespace: myagents-beta
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
    syncOptions:
      - CreateNamespace=true
```

### 2. Application ArgoCD - environnement preview (PR)

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: myagents-preview
  namespace: argocd
spec:
  project: default
  source:
    repoURL: https://github.com/ia-generative/myagents
    targetRevision: main
    path: helm/
    helm:
      valuesFiles:
        - values.yaml
        - values-preview.yaml
  destination:
    server: https://kubernetes.default.svc
    namespace: myagents-preview
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
    syncOptions:
      - CreateNamespace=true
```

### 3. Application ArgoCD - production

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: myagents-prod
  namespace: argocd
spec:
  project: default
  source:
    repoURL: https://github.com/ia-generative/myagents
    targetRevision: main
    path: helm/
    helm:
      valuesFiles:
        - values.yaml
        - values-prod.yaml
  destination:
    server: https://kubernetes.default.svc
    namespace: myagents-prod
  syncPolicy:
    automated:
      prune: true
      selfHeal: false  # Sync manuel en production
    syncOptions:
      - CreateNamespace=true
```

## Déploiement en ligne de commande

### Environnement beta

```bash
helm install myagents-beta helm/ \
  -f helm/values.yaml \
  -f helm/values-beta.yaml \
  -n myagents-beta \
  --create-namespace
```

### Environnement preview

```bash
helm install myagents-preview helm/ \
  -f helm/values.yaml \
  -f helm/values-preview.yaml \
  -n myagents-preview \
  --create-namespace
```

### Production

```bash
helm install myagents-prod helm/ \
  -f helm/values.yaml \
  -f helm/values-prod.yaml \
  --set app.image.tag=v1.2.3 \
  -n myagents-prod \
  --create-namespace
```

## Variables d'environnement

### Image PostgreSQL

Pour utiliser une version différente de PostgreSQL en production, surcharger dans ArgoCD :

```yaml
parameters:
  - name: postgres.image.tag
    value: "18.5-alpine"  # Par défaut : 18.6-alpine
```

### Registry personnalisé

Pour utiliser un registre Docker différent :

```yaml
helm:
  parameters:
    - name: app.image.registry
      value: "docker.io"
    - name: app.image.repository
      value: "myorg/mes-agents"
```

## Secrets PostgreSQL

En production, le mot de passe PostgreSQL doit être géré via un secret Kubernetes :

```bash
# Créer le secret
kubectl create secret generic postgres-secret \
  --from-literal=password=<your-secure-password> \
  -n myagents-prod

# Le chart utilise ce secret si `postgres.existingSecret` est défini
```

Dans `values-prod.yaml`, c'est déjà configuré :

```yaml
postgres:
  existingSecret: "postgres-secret"
  existingSecretKey: "password"
```

## Mise à jour de déploiement

### Mise à jour du tag d'image (CD pipeline)

Le pipeline CI/CD construit l'image avec le tag de version :

```bash
IMAGE_NAME: ghcr.io/${{ github.repository }}/mes-agents
IMAGE_TAG: ${{ needs.release.outputs.version }}  # v1.2.3
```

Pour mettre à jour le déploiement avec cette image :

1. **Automatiquement via ArgoCD** : L'image est taguée au build, ArgoCD sync automatiquement
2. **Via script CI/CD** : Le pipeline peut patcher le tag ArgoCD Application après le build

Exemple de mise à jour via `kubectl patch` :

```bash
kubectl patch application myagents-prod \
  -n argocd \
  --type merge \
  -p '{"spec":{"source":{"helm":{"parameters":[{"name":"app.image.tag","value":"v1.2.3"}]}}}}'
```

## Déploiement sur Cloud Pi Native (CPiN)

### Prérequis

- Cluster Kubernetes avec Vault Static Secrets Operator installé
- Vault configuré avec un mount KV-v2 à `kv`
- CRD `VaultAuth` nommé `vault-auth` créé dans chaque namespace cible
- Policy Vault autorisant `myagents/<env>/app` pour chaque environnement

### Déploiement des secrets Vault

Avant de déployer le chart, s'assurer que :

1. Les secrets existent dans Vault :
   - `myagents/beta/app` → `LLM_API_KEY`, `OPENWEBUI_API_KEY`
   - `myagents/preview/app` → `LLM_API_KEY`, `OPENWEBUI_API_KEY`
   - `myagents/prod/app` → `LLM_API_KEY`, `OPENWEBUI_API_KEY`

2. Le Vault Static Secrets Operator crée les secrets Kubernetes `myagents-secrets`

3. Le Deployment `mes-agents` injecte ces secrets via `valueFrom.secretKeyRef`

### Vérifications post-déploiement

```bash
# Vérifier les VaultStaticSecret
kubectl get vaultstaticsecret -n myagents-prod

# Vérifier que le secret Kubernetes est créé
kubectl get secret myagents-secrets -n myagents-prod

# Vérifier que les secrets sont dans le pod
kubectl exec -it <pod-name> -n myagents-prod -- env | grep API_KEY
```

## Troubleshooting

### Vérifier le rendu des templates

```bash
helm template myagents helm/ \
  -f helm/values.yaml \
  -f helm/values-prod.yaml \
  --debug
```

### Valider la configuration

```bash
helm lint helm/ -f helm/values-prod.yaml
```

### Mises à jour des dépendances Helm

```bash
helm dependency update helm/
```

Cela télécharge le sub-chart PostgreSQL de Cloudpirates.
