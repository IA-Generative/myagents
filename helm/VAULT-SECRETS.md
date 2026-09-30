# Configuration des secrets dans Vault

Ce document explique comment configurer les secrets dans Vault pour les déploiements Helm.

## Structure des secrets

Les secrets sont organisés par environnement et par service dans Vault :

```
kv/
├── myagents/
│   ├── prod/
│   │   ├── app/          → Secrets application
│   │   └── postgres/     → Secrets PostgreSQL
│   ├── beta/
│   │   ├── app/
│   │   └── postgres/
│   └── preview/
│       ├── app/
│       └── postgres/
```

## Secrets application (`app`)

Ces secrets contiennent les clés API et tokens nécessaires pour l'application.

### Clés requises

- **`LLM_API_KEY`** : Clé API pour le service LLM (OpenAI, etc.)
- **`OPENWEBUI_API_KEY`** : Clé API pour OpenWebUI

### Exemple de création (Vault CLI)

```bash
# Production
vault kv put kv/myagents/prod/app \
  LLM_API_KEY='sk-proj-xxx' \
  OPENWEBUI_API_KEY='sk-xxx'

# Beta
vault kv put kv/myagents/beta/app \
  LLM_API_KEY='sk-proj-xxx' \
  OPENWEBUI_API_KEY='sk-xxx'

# Preview
vault kv put kv/myagents/preview/app \
  LLM_API_KEY='sk-proj-xxx' \
  OPENWEBUI_API_KEY='sk-xxx'
```

## Secrets PostgreSQL (`postgres`)

Ces secrets contiennent les mots de passe PostgreSQL pour l'accès à la base de données.

### Clés requises

- **`password`** : Mot de passe pour l'utilisateur applicatif (p.ex. `mesagents`)
  - Doit correspondre à la valeur de `postgres.username` dans les values
  - Utilisé par l'application pour se connecter à la base
  
- **`postgres_root_password`** : Mot de passe pour l'utilisateur root PostgreSQL
  - Utilisé par PostgreSQL lors de l'initialisation
  - Nécessaire pour les migrations et opérations administrateur

### Champs additionnels (optionnels)

- **`uri`** : URL de connexion complète (format: `postgresql://user:password@host:port/database`)
  - Généré automatiquement par le chart si non fourni
  - Format: `postgresql://mesagents:<password>@postgres:5432/<database>`

### Exemple de création (Vault CLI)

```bash
# Production
vault kv put kv/myagents/prod/postgres \
  password='prod-secure-password-xyz' \
  postgres_root_password='prod-root-password-abc'

# Beta
vault kv put kv/myagents/beta/postgres \
  password='beta-secure-password-xyz' \
  postgres_root_password='beta-root-password-abc'

# Preview
vault kv put kv/myagents/preview/postgres \
  password='preview-secure-password-xyz' \
  postgres_root_password='preview-root-password-abc'
```

## Configuration Vault pour chaque environnement

### Production (`myagents/prod/`)

```bash
# Secrets application
vault kv put kv/myagents/prod/app \
  LLM_API_KEY='votre-cle-api-prod' \
  OPENWEBUI_API_KEY='votre-cle-openwebui-prod'

# Secrets PostgreSQL
vault kv put kv/myagents/prod/postgres \
  password='mot-de-passe-app-prod' \
  postgres_root_password='mot-de-passe-root-prod'
```

### Beta/Preprod (`myagents/beta/`)

```bash
# Secrets application
vault kv put kv/myagents/beta/app \
  LLM_API_KEY='votre-cle-api-beta' \
  OPENWEBUI_API_KEY='votre-cle-openwebui-beta'

# Secrets PostgreSQL
vault kv put kv/myagents/beta/postgres \
  password='mot-de-passe-app-beta' \
  postgres_root_password='mot-de-passe-root-beta'
```

### Preview/Pull Requests (`myagents/preview/`)

```bash
# Secrets application
vault kv put kv/myagents/preview/app \
  LLM_API_KEY='votre-cle-api-preview' \
  OPENWEBUI_API_KEY='votre-cle-openwebui-preview'

# Secrets PostgreSQL
vault kv put kv/myagents/preview/postgres \
  password='mot-de-passe-app-preview' \
  postgres_root_password='mot-de-passe-root-preview'
```

## Policy Vault

Pour que le Vault Secrets Operator puisse lire ces secrets, une policy Vault est nécessaire :

```hcl
# Policy pour myagents-prod
path "kv/data/myagents/prod/*" {
  capabilities = ["read", "list"]
}

# Policy pour myagents-beta
path "kv/data/myagents/beta/*" {
  capabilities = ["read", "list"]
}

# Policy pour myagents-preview
path "kv/data/myagents/preview/*" {
  capabilities = ["read", "list"]
}
```

## Vérification des secrets dans Vault

```bash
# Lister les secrets d'un environnement
vault kv list kv/myagents/prod/

# Vérifier le contenu d'un secret (application)
vault kv get kv/myagents/prod/app

# Vérifier le contenu d'un secret (postgres)
vault kv get kv/myagents/prod/postgres
```

## Intégration avec Vault Secrets Operator

Une fois les secrets créés dans Vault, le Vault Secrets Operator :

1. Crée un Secret Kubernetes `myagents-secrets` à partir de `kv/myagents/<env>/app`
2. Crée un Secret Kubernetes `postgres-secret` à partir de `kv/myagents/<env>/postgres`
3. Déclenche un rollout du Deployment `mes-agents` et de la StatefulSet `postgres`

### Vérification dans le cluster Kubernetes

```bash
# Vérifier que les VaultStaticSecret sont créés
kubectl get vaultstaticsecret -n myagents-prod

# Vérifier que les secrets Kubernetes sont synchronisés
kubectl get secret -n myagents-prod | grep secrets

# Afficher les clés du secret (sans les valeurs)
kubectl describe secret myagents-secrets -n myagents-prod

# Vérifier que le secret postgres est utilisé
kubectl describe secret postgres-secret -n myagents-prod
```

## Mise à jour des secrets

Pour mettre à jour un secret dans Vault :

```bash
# Mettre à jour la clé LLM_API_KEY
vault kv patch kv/myagents/prod/app \
  LLM_API_KEY='nouvelle-cle-api'

# Mettre à jour le mot de passe PostgreSQL
vault kv patch kv/myagents/prod/postgres \
  password='nouveau-mot-de-passe'
```

Le Vault Secrets Operator synchronisera automatiquement les changements dans Kubernetes et déclenchera un rollout.

## Bonnes pratiques

1. **Secrets forts** : Utiliser des mots de passe/clés générés aléatoirement et complexes
2. **Rotation** : Définir une politique de rotation régulière des secrets (tous les 90 jours)
3. **Audit** : Activer l'audit dans Vault pour tracer l'accès aux secrets
4. **Séparation** : Utiliser des secrets différents pour chaque environnement
5. **Backup** : Sauvegarder régulièrement Vault ou utiliser un replicat
6. **Revue** : Auditer régulièrement l'accès aux secrets et les policies Vault

## Troubleshooting

### Secret non synchronisé dans Kubernetes

1. Vérifier que le VaultStaticSecret existe :
   ```bash
   kubectl describe vaultstaticsecret myagents-secrets -n myagents-prod
   ```

2. Vérifier les logs du Vault Secrets Operator :
   ```bash
   kubectl logs -n vault deployment/secrets-operator
   ```

3. Vérifier la policy Vault autorisant la lecture :
   ```bash
   vault policy read myagents-prod
   ```

### Le pod ne reçoit pas les secrets

1. Vérifier que les secrets Kubernetes existent :
   ```bash
   kubectl get secret -n myagents-prod
   ```

2. Vérifier la configuration d'injection dans le Deployment :
   ```bash
   kubectl get deployment mes-agents -n myagents-prod -o yaml | grep -A 10 envSecret
   ```

3. Redéployer manuellement si nécessaire :
   ```bash
   kubectl rollout restart deployment/mes-agents -n myagents-prod
   ```
