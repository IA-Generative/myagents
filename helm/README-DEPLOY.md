# Helm Chart Deployment Guide

Ce répertoire contient le chart Helm pour déployer `myagents` sur Kubernetes.

**⚠️ Important** : Ce dépôt est PUBLIC. Les configurations sensibles (credentials, secrets Vault, domaines, etc.) sont gérées dans un dépôt PRIVÉ séparé.

Voir **[HELM-ARCHITECTURE.md](./HELM-ARCHITECTURE.md)** pour la stratégie complète de gestion multi-répos.

## Structure rapide

```
helm/
├── Chart.yaml                    ← Métadonnées du chart
├── values.yaml                   ← Scaffold minimal (PUBLIC)
├── templates/                    ← Templates Helm (PUBLIC)
├── examples/                     ← Exemples de configuration
│   ├── common.yaml               ← À copier dans le dépôt privé
│   ├── values-prod.yaml
│   ├── values-beta.yaml
│   └── values-preview.yaml
├── HELM-ARCHITECTURE.md          ← Architecture multi-répos (LIRE EN PREMIER!)
└── README-DEPLOY.md              ← Ce fichier
```

## ⚡ Démarrage rapide

### 1. Créer le dépôt de configuration privé

```bash
# Créer un dépôt privé (par exemple: myagents-config)
git clone git@github.com:internal/myagents-config.git
cd myagents-config

# Copier les fichiers d'exemple
cp /path/to/helm/examples/common.yaml .
cp /path/to/helm/examples/values-*.yaml .

# Ajouter vos configurations sensibles
# - Domaines réels
# - Chemins Vault
# - Variables d'environnement

git add .
git commit -m "Initial Helm configuration"
git push
```

### 2. Déployer via Helm

```bash
# Cloner les deux dépôts
git clone https://github.com/ia-generative/myagents.git
git clone git@github.com:internal/myagents-config.git

# Déployer en production
helm upgrade --install myagents-prod ./myagents/helm \
  -f myagents-config/common.yaml \
  -f myagents-config/values-prod.yaml \
  -n myagents-prod \
  --create-namespace
```

### 3. Déployer via ArgoCD

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: myagents-prod
spec:
  source:
    repoURL: https://github.com/ia-generative/myagents.git
    path: helm/
    helm:
      valuesFiles:
        # ⚠️ À configurer dans votre cluster ArgoCD
        - https://github.com/internal/myagents-config/raw/main/common.yaml
        - https://github.com/internal/myagents-config/raw/main/values-prod.yaml
  destination:
    server: https://kubernetes.default.svc
    namespace: myagents-prod
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
```

## 📚 Documentation détaillée

### Configuration & Secrets

- **[HELM-ARCHITECTURE.md](./HELM-ARCHITECTURE.md)** - Architecture multi-répos complète
- **[VAULT-SECRETS.md](../VAULT-SECRETS.md)** - Configuration Vault (dans le dépôt privé)

### Fichiers d'exemple

Dans le dépôt PUBLIC, le dossier `examples/` contient les modèles :

```bash
# Voir les fichiers d'exemple
ls -la helm/examples/
```

Copiez-les dans votre dépôt PRIVÉ et adaptez-les à vos besoins.

## 🔐 Principes de sécurité

| ✅ Public (ce dépôt) | 🔒 Privé (autre dépôt) |
|---|---|
| Chart Helm générique | Configurations spécifiques |
| `values.yaml` minimal | `common.yaml` + `values-<env>.yaml` |
| Templates | Secrets, domaines, tags d'image |
| Documentations | Vault paths, credentials |

**JAMAIS COMMITTER DANS LE DÉPÔT PUBLIC:**
- Secrets ou credentials
- Domaines de production
- Tags d'image spécifiques
- Chemins Vault
- Références à des secrets existants

## 🚀 Déploiement en ligne de commande

### Environnement Production

```bash
# Récupérer les values du dépôt privé
wget https://github.com/internal/myagents-config/raw/main/common.yaml
wget https://github.com/internal/myagents-config/raw/main/values-prod.yaml

# Déployer
helm upgrade --install myagents-prod ./helm \
  -f common.yaml \
  -f values-prod.yaml \
  -n myagents-prod \
  --create-namespace
```

### Environnement Beta/Staging

```bash
helm upgrade --install myagents-beta ./helm \
  -f common.yaml \
  -f values-beta.yaml \
  -n myagents-beta \
  --create-namespace
```

### Environnement Preview (Pull Requests)

```bash
helm upgrade --install myagents-preview ./helm \
  -f common.yaml \
  -f values-preview.yaml \
  -n myagents-preview \
  --create-namespace
```

## ✓ Vérifications avant déploiement

### 1. Valider la syntaxe Helm

```bash
# Linter
helm lint ./helm

# Vérifier le rendu des templates
helm template myagents ./helm \
  -f common.yaml \
  -f values-prod.yaml \
  --debug
```

### 2. Vérifier les secrets Kubernetes

```bash
# Vérifier que les Secrets Kubernetes existent
kubectl get secret -n myagents-prod | grep -E "myagents-secrets|postgres-secret"

# Vérifier que les VaultStaticSecret sont synchro
kubectl get vaultstaticsecret -n myagents-prod
```

### 3. Vérifier les variables d'environnement

```bash
# Lister les variables du pod
kubectl exec -it <pod-name> -n myagents-prod -- env | grep -E "ENVIRONMENT|QDRANT|LLM"
```

## 🔧 Mise à jour du chart

### Mettre à jour les dépendances

```bash
helm dependency update ./helm
```

### Mettre à jour le tag d'image

```bash
# Via Helm command line
helm upgrade myagents ./helm \
  -f common.yaml \
  -f values-prod.yaml \
  --set app.image.tag=v1.2.3 \
  -n myagents-prod

# Via ArgoCD (patch Application)
kubectl patch application myagents-prod \
  -n argocd \
  --type merge \
  -p '{"spec":{"source":{"helm":{"parameters":[{"name":"app.image.tag","value":"v1.2.3"}]}}}}'
```

## 🐛 Troubleshooting

### Erreur : "chart requires postgres but it's not enabled"

Assurez-vous que `postgres.enabled: true` est défini dans votre `common.yaml` ou `values-<env>.yaml`.

### Secrets non disponibles dans le pod

```bash
# Vérifier que les Secret Kubernetes existent
kubectl describe secret myagents-secrets -n myagents-prod

# Vérifier que le Deployment référence les secrets
kubectl describe deployment mes-agents -n myagents-prod | grep -A 10 "valueFrom"

# Redémarrer le Deployment si nécessaire
kubectl rollout restart deployment/mes-agents -n myagents-prod
```

### Erreur de rendu Helm : "undefined variable"

Vérifier que tous les `.env` utilisés dans les templates sont définis dans les values :

```bash
# Chercher les variables non définies
helm template myagents ./helm \
  -f common.yaml \
  -f values-prod.yaml \
  2>&1 | grep "undefined"
```

## 📊 Statut du déploiement

```bash
# Vérifier le statut du déploiement
kubectl rollout status deployment/mes-agents -n myagents-prod

# Voir les événements récents
kubectl describe deployment mes-agents -n myagents-prod

# Logs du pod
kubectl logs -f deployment/mes-agents -n myagents-prod
```

## 🔄 Synchronisation ArgoCD

### Vérifier le statut

```bash
# Vérifier l'Application ArgoCD
kubectl describe application myagents-prod -n argocd

# Regarder les logs du repo server
kubectl logs -n argocd deployment/argocd-repo-server | grep myagents
```

### Forcer la synchronisation

```bash
# Sync manuel
argocd app sync myagents-prod

# Ou via kubectl
kubectl patch application myagents-prod \
  -n argocd \
  --type merge \
  -p '{"status":{"operationState":{"finishedAt":null}}}'
```

## 📝 Variables d'environnement requises

Ces variables DOIVENT être définies dans `values-<env>.yaml` (dépôt privé):

| Variable | Exemple | Où définir |
|----------|---------|-----------|
| `ENVIRONMENT` | `production` | `app.env.ENVIRONMENT` |
| `QDRANT_URL` | `http://qdrant:6333` | `app.env.QDRANT_URL` |
| `LLM_BASE_URL` | `https://api.openai.com` | `app.env.LLM_BASE_URL` |
| `LLM_DEFAULT_MODEL` | `gpt-4` | `app.env.LLM_DEFAULT_MODEL` |
| `LLM_EMBEDDING_MODEL` | `text-embedding-3-large` | `app.env.LLM_EMBEDDING_MODEL` |
| `CORS_ORIGINS` | `["https://mes-agents.com"]` | `app.env.CORS_ORIGINS` |
| `LLM_API_KEY` | (secret) | `app.envSecret.LLM_API_KEY` |
| `OPENWEBUI_API_KEY` | (secret) | `app.envSecret.OPENWEBUI_API_KEY` |

## 📖 Références

- [Helm Documentation](https://helm.sh/docs/)
- [Kubernetes Values Files](https://helm.sh/docs/chart_template_guide/values/)
- [ArgoCD Source Management](https://argo-cd.readthedocs.io/en/stable/user-guide/private-repositories/)
- [Chart Dependencies](https://helm.sh/docs/helm/helm_dependency/)
