# Architecture Helm Multi-Répos

Ce document explique la stratégie de gestion des configurations Helm pour un dépôt PUBLIC avec des configurations PRIVÉES et sensibles.

## Principes

1. **Dépôt public** : Contient UNIQUEMENT le chart Helm générique (templates + `values.yaml` minimal)
2. **Dépôt privé** : Contient toutes les configurations sensibles et spécifiques par environnement
3. **Séparation des responsabilités** : 
   - Chart = logique applicative universelle
   - Values = configuration spécifique au projet

## Structure des dépôts

### Dépôt PUBLIC (mirai/nextapps/myagents)

```
helm/
├── Chart.yaml
├── values.yaml                  ← Minimal scaffold seulement
├── templates/
│   ├── deployment.yaml
│   ├── service.yaml
│   ├── ingress.yaml
│   ├── vault.yaml
│   └── ...
├── charts/                       ← Sub-charts (postgres, etc.)
├── README-DEPLOY.md
├── HELM-ARCHITECTURE.md          ← Ce fichier
└── examples/
    ├── common.yaml               ← Exemple de configuration commune
    ├── values-prod.yaml          ← Exemple pour production
    ├── values-beta.yaml          ← Exemple pour beta
    └── values-preview.yaml       ← Exemple pour preview
```

### Dépôt PRIVÉ (exemple: myagents-config)

```
helm-config/
├── common.yaml                   ← Configuration commune à tous les envs
├── values-prod.yaml
├── values-beta.yaml
├── values-preview.yaml
├── VAULT-SECRETS.md             ← Documentation secrète
└── .gitignore
    ├── *.secret.yaml
    └── .env*
```

## Contenu des fichiers

### `values.yaml` (PUBLIC - Minimal)

```yaml
# ✅ À inclure
app:
  replicaCount: 1
  image:
    registry: ""
    repository: ""
    tag: ""
  containerPort: 8000
  resources:
    requests:
      memory: "256Mi"
      cpu: "100m"

postgres:
  enabled: false
  username: ""
  database: ""
  password: ""
  existingSecret: ""

vaultSecrets:
  enabled: false
  mount: "kv"
  basePath: ""
  items: []
```

```yaml
# ❌ À ÉVITER
# Ne PAS inclure :
# - Image tags spécifiques
# - Domaines/DNS
# - Chemins Vault
# - Ressources spécifiques par environnement
# - Secrets ou credentials (même commentés)
# - Références à des secrets existants hardcodés
```

### `common.yaml` (PRIVÉ - Partagé)

Configuration **non-sensible** commune à tous les environnements :

```yaml
app:
  image:
    registry: "ghcr.io"
    repository: "ia-generative/myagents/mes-agents"
    pullPolicy: "IfNotPresent"
  
  securityContext:
    runAsNonRoot: true
    allowPrivilegeEscalation: false
    # ...
  
  probes:
    startupProbe: { ... }
    readinessProbe: { ... }
    livenessProbe: { ... }
  
  service:
    enabled: true
    type: "ClusterIP"
    port: 80

postgres:
  enabled: true
  image:
    tag: "18.6-alpine"
  persistence:
    enabled: true

vaultSecrets:
  mount: "kv"
```

### `values-<env>.yaml` (PRIVÉ - Spécifique)

Configuration sensible et spécifique par environnement :

```yaml
app:
  replicaCount: 3                    # Prod: 3, Beta: 1, Preview: 1
  image:
    tag: "v1.2.3"                    # Défini par CD pipeline
  
  resources:                         # Différent par environnement
    requests:
      memory: "512Mi"
      cpu: "250m"
  
  env:
    ENVIRONMENT: "production"
    QDRANT_URL: "http://qdrant:6333"
    LLM_BASE_URL: "https://api.openai.com"
    CORS_ORIGINS: '["https://mes-agents.prod.com"]'
  
  envSecret:                         # Références aux secrets Vault
    LLM_API_KEY:
      secretKeyRef:
        name: "myagents-secrets"
        key: "LLM_API_KEY"
  
  ingress:
    enabled: true
    hosts:
      - name: "mes-agents.prod.com"

postgres:
  username: "mesagents"
  existingSecret: "postgres-secret"
  persistence:
    size: 10Gi
    storageClass: "fast-ssd"

vaultSecrets:
  basePath: "myagents/prod"
  items:
    - subPath: "app"
      destination:
        name: "myagents-secrets"
    - subPath: "postgres"
      destination:
        name: "postgres-secret"
```

## Workflow de déploiement

### 1. Setup initial (administrateur)

```bash
# Cloner les deux dépôts
git clone https://github.com/ia-generative/myagents.git
git clone git@github.com:internal/myagents-config.git  # Privé

# Structurer les configs privées
cd myagents-config/
# Créer common.yaml, values-prod.yaml, etc.
git add .
git commit -m "Initial Helm configuration"
git push
```

### 2. Déploiement via ArgoCD

**Option A : Monorepo Helm avec ArgoCD**

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
      releaseName: myagents
      valuesFiles:
        # Sources multiples depuis deux dépôts
        - https://github.com/internal/myagents-config/raw/main/common.yaml
        - https://github.com/internal/myagents-config/raw/main/values-prod.yaml
  destination:
    server: https://kubernetes.default.svc
    namespace: myagents-prod
```

**Option B : Plugin ArgoCD personnalisé (recommandé)**

```yaml
apiVersion: argoproj.io/v1alpha1
kind: ConfigManagementPlugin
metadata:
  name: helm-multi-repos
spec:
  version: 1
  generate:
    command: [sh, -c]
    args:
      - |
        # Télécharger les valeurs du dépôt privé
        curl -s https://github.com/internal/myagents-config/raw/main/common.yaml > /tmp/common.yaml
        curl -s https://github.com/internal/myagents-config/raw/main/values-prod.yaml > /tmp/values-prod.yaml
        
        # Générer les manifests
        helm template $ARGOCD_APP_NAME ./helm \
          -f /tmp/common.yaml \
          -f /tmp/values-prod.yaml
```

### 3. Déploiement en ligne de commande

```bash
# Récupérer les values du dépôt privé
curl -o common.yaml https://github.com/internal/myagents-config/raw/main/common.yaml
curl -o values-prod.yaml https://github.com/internal/myagents-config/raw/main/values-prod.yaml

# Installer/mettre à jour
helm upgrade --install myagents ./helm \
  -f common.yaml \
  -f values-prod.yaml \
  -n myagents-prod \
  --create-namespace
```

### 4. CI/CD Pipeline (déploiement automatique)

```yaml
# .github/workflows/deploy.yml
jobs:
  deploy:
    steps:
      # Cloner le dépôt public (déjà dans le checkout)
      - uses: actions/checkout@v4
      
      # Cloner le dépôt privé avec credentials
      - run: |
          git clone https://${{ secrets.GITHUB_PAT }}@github.com/internal/myagents-config.git /tmp/config
      
      # Déployer avec ArgoCD
      - run: |
          helm template myagents ./helm \
            -f /tmp/config/common.yaml \
            -f /tmp/config/values-${{ env.ENVIRONMENT }}.yaml \
            | kubectl apply -f -
```

## Gestion des secrets Vault

### Structure Vault (dans le dépôt PRIVÉ)

Voir `VAULT-SECRETS.md` du dépôt privé pour les chemins et clés.

### Synchronisation des secrets

```bash
# 1. Créer les secrets dans Vault (dépôt privé)
vault kv put kv/myagents/prod/app \
  LLM_API_KEY='sk-...' \
  OPENWEBUI_API_KEY='sk-...'

vault kv put kv/myagents/prod/postgres \
  password='pwd' \
  postgres_root_password='root-pwd'

# 2. VaultStaticSecret Operator synchronise dans K8s
# (configuré via vaultSecrets.items dans values-prod.yaml)

# 3. Les Secrets Kubernetes sont injectés dans les pods
# (configurés via envSecret dans values-prod.yaml)
```

## Avantages de cette architecture

| Aspect | Bénéfice |
|--------|----------|
| **Sécurité** | Zéro secret dans le dépôt public |
| **Flexibilité** | Configurations spécifiques par équipe/client |
| **Maintenabilité** | Séparation claire entre code et config |
| **Scalabilité** | Support multi-projets facilement |
| **Conformité** | Audit des accès à la config privée |
| **Versionning** | Historique séparé public/privé |

## Bonnes pratiques

### Dans le dépôt PUBLIC

✅ **À faire**
- Garder `values.yaml` minimal (scaffold seulement)
- Documenter chaque paramètre possible
- Inclure des exemples dans `./examples/`
- Versioner le chart avec un Chart.yaml explicitant les dépendances
- Tester les templates Helm sans values (ou avec values minimales)

❌ **À éviter**
- Ne pas committer de credentials
- Ne pas hardcoder les domaines/DNS
- Ne pas inclure les tags d'image de prod
- Ne pas committer des secrets même en commentaires

### Dans le dépôt PRIVÉ

✅ **À faire**
- Protéger l'accès (private repo, branch protection)
- Documenter Vault et les chemins des secrets
- Versionner comme le code (tags, releases)
- Audit trail des modifications
- Sauvegardes régulières

❌ **À éviter**
- Ne pas partager le dépôt largement
- Ne pas committer les plaintext de vrais secrets (utiliser Vault)
- Ne pas ignorer les secrets dans `.gitignore`

## Troubleshooting

### Erreur : "values not found"

```bash
# Vérifier que les fichiers values existent
curl -I https://github.com/internal/myagents-config/raw/main/values-prod.yaml

# Vérifier les permissions du token GitHub
# ou utiliser SSH keys avec le dépôt privé
```

### Values ne se synchronisent pas via ArgoCD

```bash
# Vérifier la configuration du plugin ArgoCD
kubectl describe configmap argocd-cm -n argocd

# Regarder les logs d'ArgoCD
kubectl logs -n argocd deployment/argocd-repo-server

# Tester manuellement le template
helm template myagents ./helm \
  -f values-prod.yaml \
  --debug
```

### Secrets Vault non injectés

```bash
# Vérifier les VaultStaticSecret
kubectl get vaultstaticsecret -n myagents-prod

# Vérifier les Secrets Kubernetes créés
kubectl get secret -n myagents-prod

# Vérifier les logs du Vault Secrets Operator
kubectl logs -n vault deployment/secrets-operator
```

## Migration depuis une architecture centralisée

Si vous avez actuellement tous les values dans le dépôt public :

1. **Créer le dépôt privé** avec la structure recommandée
2. **Copier les fichiers** de `helm/values*.yaml` vers le dépôt privé
3. **Remplacer** les fichiers publics par les versions minimales (scaffold)
4. **Mettre à jour** les pipelines CI/CD et ArgoCD
5. **Tester** chaque environnement avant de fermer les accès publics
6. **Archiver** les anciennes branches si nécessaire

## Références

- [Helm Values Documentation](https://helm.sh/docs/chart_template_guide/values/)
- [ArgoCD Source Management](https://argo-cd.readthedocs.io/en/stable/user-guide/private-repositories/)
- [Vault Secrets Operator](https://developer.hashicorp.com/vault/docs/platform/k8s/vso)
