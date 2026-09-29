# Helm Chart Deployment Guide

Ce répertoire contient le chart Helm pour déployer `mes-agents` sur Kubernetes via ArgoCD.

## Structure des fichiers values

- **`values.yaml`** : Configuration de base, portée par défaut
- **`values-dev.yaml`** : Surcharges pour développement local
- **`values-staging.yaml`** : Surcharges pour l'environnement staging
- **`values-prod.yaml`** : Surcharges pour la production

## Déploiement avec ArgoCD

### 1. Application ArgoCD simple (développement)

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: mes-agents-dev
  namespace: argocd
spec:
  project: default
  source:
    repoURL: https://github.com/wayii/mi-sdid/repos/mes-agents-private
    targetRevision: main
    path: helm/
    helm:
      valuesFiles:
        - values.yaml
        - values-dev.yaml
  destination:
    server: https://kubernetes.default.svc
    namespace: mes-agents-dev
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
    syncOptions:
      - CreateNamespace=true
```

### 2. Application ArgoCD pour staging

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: mes-agents-staging
  namespace: argocd
spec:
  project: default
  source:
    repoURL: https://github.com/wayii/mi-sdid/repos/mes-agents-private
    targetRevision: main
    path: helm/
    helm:
      valuesFiles:
        - values.yaml
        - values-staging.yaml
      # Optionnel : surcharger le tag d'image via ArgoCD
      # parameters:
      #   - name: app.image.tag
      #     value: v1.2.3
  destination:
    server: https://kubernetes.default.svc
    namespace: mes-agents-staging
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
    syncOptions:
      - CreateNamespace=true
```

### 3. Application ArgoCD pour production

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: mes-agents-prod
  namespace: argocd
spec:
  project: default
  source:
    repoURL: https://github.com/wayii/mi-sdid/repos/mes-agents-private
    targetRevision: main
    path: helm/
    helm:
      valuesFiles:
        - values.yaml
        - values-prod.yaml
      # Surcharger le tag d'image pour chaque release
      parameters:
        - name: app.image.tag
          value: v1.2.3  # À remplacer par la version réelle
  destination:
    server: https://kubernetes.default.svc
    namespace: mes-agents-prod
  syncPolicy:
    automated:
      prune: true
      selfHeal: false  # Sync manuel en production
    syncOptions:
      - CreateNamespace=true
```

## Déploiement en ligne de commande

### Développement

```bash
helm install mes-agents helm/ \
  -f helm/values.yaml \
  -f helm/values-dev.yaml \
  -n mes-agents-dev \
  --create-namespace
```

### Staging

```bash
helm install mes-agents helm/ \
  -f helm/values.yaml \
  -f helm/values-staging.yaml \
  -n mes-agents-staging \
  --create-namespace
```

### Production

```bash
helm install mes-agents helm/ \
  -f helm/values.yaml \
  -f helm/values-prod.yaml \
  --set app.image.tag=v1.2.3 \
  -n mes-agents-prod \
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

En production, la password PostgreSQL doit être gérée via un secret Kubernetes :

```bash
# Créer le secret
kubectl create secret generic postgres-secret \
  --from-literal=password=<your-secure-password> \
  -n mes-agents-prod

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

1. **Manuellement via ArgoCD UI** : Modifier le paramètre `app.image.tag` dans l'Application
2. **Automatiquement via Renovate/Dependabot** : Si configuré pour mettre à jour les images
3. **Via script CI/CD** : Le pipeline peut patcher le tag ArgoCD Application après le build

Exemple de mise à jour via `kubectl patch` :

```bash
kubectl patch application mes-agents-prod \
  -n argocd \
  --type merge \
  -p '{"spec":{"source":{"helm":{"parameters":[{"name":"app.image.tag","value":"v1.2.3"}]}}}}'
```

## Troubleshooting

### Vérifier le rendu des templates

```bash
helm template mes-agents helm/ \
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
