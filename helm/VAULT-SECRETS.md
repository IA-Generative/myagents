# Configuration des secrets dans Vault

Ce document explique comment configurer les secrets dans Vault pour les déploiements Helm.

## Structure des secrets

Les secrets sont organisés par environnement et par service dans Vault :

```
kv/
├── prod/
│   ├── myagents/
│   │   ├── app/          → Secrets application
│   │   └── postgres/     → Secrets PostgreSQL
│   ├── myportail/
│       ├── app/
│       └── postgres/
├── preview/
│   ├── myagents/
│   │   ├── app/          → Secrets application
│   │   └── postgres/     → Secrets PostgreSQL
│   ├── myportail/
│       ├── app/
│       └── postgres/
```

## Secrets application (`app`)

Ces secrets sont lus par le serveur FastAPI (`apps/server/app/core/config.py`). Le Secret `myagents-secrets` est injecté en entier dans le pod via `app.envFromSecrets` : toute clé Vault devient une variable d'environnement du même nom.

### Mapping variables d'env ↔ config.py

Les variables d'env Kubernetes (synced depuis Vault) correspondent exactement aux champs Pydantic de `apps/server/app/core/config.py`. **Aucun default** dans `config.py` : Vault DOIT fournir une valeur.

| Variable d'env | Champ Pydantic | Type | Obligatoire | Exemple | Notes |
|---|---|---|---|---|---|
| `OPENAI_BASE_URL` | `openai_base_url` | str | ✓ | `https://api.scaleway.com/llm/v1` ou `http://localhost:11434/v1` | Endpoint LLM compatible OpenAI |
| `OPENAI_API_KEY` | `openai_api_key` | str | ✓ | `sk-xxx` ou `""` (vide si auth non requise) | Clé API du provider LLM |
| `LLM_DEFAULT_MODEL` | `llm_default_model` | str | ✓ | `gpt-4`, `gpt-oss-120b`, `mistral-7b` | Modèle de fallback (aucun default) |
| `LLM_EMBEDDING_MODEL` | `llm_embedding_model` | str | ✓ | `text-embedding-3-large`, `nomic-embed-text` | Modèle d'embedding pour RAG |
| `LLM_ASSIST_MODEL` | `llm_assist_model` | str | ✓ | `gpt-4-turbo` | Modèle du wizard de rédaction |
| `LLM_ONBOARDING_MODEL` | `llm_onboarding_model` | str | ✓ | `mistral-small-3.2-24b-instruct-2506` | Modèle de l'onboarding |
| `DATABASE_URL` | `database_url` | str | ✓ | `postgresql://...` | URL PostgreSQL, convertie en `postgresql+asyncpg://` par le serveur |
| `OIDC_ISSUER` | `oidc_issuer` | str | ✓ | `https://keycloak.example.com/realms/myagents` | Claim `iss` exact des tokens |
| `OIDC_CLIENT_SECRET` | `oidc_client_secret` | str | ✓ | `xxx` | Secret du client Keycloak `myagents-server` |
| `OPENWEBUI_API_KEY` | `openwebui_api_key` | str | ✓ | `xxx` | Secret partagé pour `/v1/*` |
| `SESSION_SECRET` | `session_secret` | str | (optionnel*) | `xxx` | Chiffrement des tokens en base ; fallback = `oidc_client_secret` |
| `PRESENTATION_LINK_SECRET` | `presentation_link_secret` | str | (optionnel*) | `xxx` | Signature des liens ; fallback = `openwebui_api_key` |

**Remarques** :
- **Aucun default Python** : Pydantic rejette si une variable obligatoire est absente → le pod échoue au démarrage
- **En dev local Docker** : Les defaults sont dans `docker-compose.yml` (bloc `environment:`) avec syntaxe `${VAR:-default}`
- **En K8s** : Vault DOIT fournir toutes les variables obligatoires
- `SESSION_SECRET` et `PRESENTATION_LINK_SECRET` ont des fallbacks Pydantic mais DOIVENT être fournies en production pour plus de sécurité

### Clés requises en Vault

### Exemple complet de création (Vault CLI)

`vault kv put` écrase le secret entier ; utiliser `vault kv patch` pour ajouter des clés.

```bash
# Production : tous les modèles LLM obligatoires
vault kv put kv/prod/myagents/app \
  OPENAI_BASE_URL='https://api.scaleway.com/llm/v1' \
  OPENAI_API_KEY='sk-xxx' \
  LLM_DEFAULT_MODEL='gpt-4' \
  LLM_EMBEDDING_MODEL='text-embedding-3-large' \
  LLM_ASSIST_MODEL='gpt-4-turbo' \
  LLM_ONBOARDING_MODEL='mistral-small-3.2-24b-instruct-2506' \
  DATABASE_URL='postgresql://user:pass@postgres-prod:5432/myagents' \
  OIDC_ISSUER='https://keycloak.prod.example.com/realms/myagents' \
  OIDC_CLIENT_SECRET='xxx' \
  OPENWEBUI_API_KEY="$(openssl rand -hex 32)" \
  SESSION_SECRET="$(openssl rand -base64 32)" \
  PRESENTATION_LINK_SECRET="$(openssl rand -hex 32)"

# Beta/Preview : mêmes variables, valeurs distinctes
vault kv put kv/beta/myagents/app \
  OPENAI_BASE_URL='https://api.scaleway.com/llm/v1' \
  OPENAI_API_KEY='sk-xxx' \
  LLM_DEFAULT_MODEL='gpt-3.5-turbo' \
  LLM_EMBEDDING_MODEL='text-embedding-3-large' \
  LLM_ASSIST_MODEL='gpt-3.5-turbo' \
  LLM_ONBOARDING_MODEL='mistral-small-3.2-24b-instruct-2506' \
  DATABASE_URL='postgresql://user:pass@postgres-beta:5432/myagents' \
  OIDC_ISSUER='https://keycloak.beta.example.com/realms/myagents' \
  OIDC_CLIENT_SECRET='xxx' \
  OPENWEBUI_API_KEY="$(openssl rand -hex 32)" \
  SESSION_SECRET="$(openssl rand -base64 32)" \
  PRESENTATION_LINK_SECRET="$(openssl rand -hex 32)"
```

### Variables non secrètes dans `app.env` (Helm values privées)

Les variables ci-dessous ne sont **pas stockées dans Vault** et doivent être définies dans les Helm values privées (`common.yaml` ou `values-<env>.yaml`). Elles sont injectées via `app.env` et **priment sur les secrets synced** (`app.env` > `envFromSecrets`).

⚠️ **IMPORTANT** : `OPENAI_BASE_URL`, `OPENAI_API_KEY` et les 4 modèles LLM (`LLM_DEFAULT_MODEL`, `LLM_EMBEDDING_MODEL`, `LLM_ASSIST_MODEL`, `LLM_ONBOARDING_MODEL`) **DOIVENT être dans Vault** (voir tableau de mapping ci-dessus). Ne les redéfinissez dans `app.env` que pour surcharger une valeur Vault en dev/test, jamais pour fournir une valeur par défaut.

```yaml
# Obligatoires
ENVIRONMENT: production         # "production" impose OIDC_ENABLED=true
OIDC_ENABLED: "true"
OIDC_CLIENT_ID: myagents-server
OIDC_AUDIENCE: myagents-api     # doit figurer dans le claim aud, ou vide pour désactiver
QDRANT_URL: http://qdrant:6333

# Optionnels (dérivés automatiquement si non définis)
OIDC_INTERNAL_URL: http://<keycloak-svc>:8080/realms/myagents   # optionnel, par défaut = OIDC_ISSUER
```

**Derivation automatique** : `WEB_PUBLIC_URL`, `PUBLIC_BASE_URL` et `CORS_ORIGINS` sont dérivés du premier host de `app.ingress.hosts` (`https://` si `app.ingress.tls` est défini). Redéfinir dans `app.env` seulement pour surcharger.

## Client Keycloak

Client confidentiel (Client authentication = On), flux Standard flow uniquement, PKCE `S256`, scopes `myagents-api` (audience) et `groups` en default scopes.
Le serveur calcule `redirect_uri = WEB_PUBLIC_URL + /api/auth/callback` et `post_logout_redirect_uri = WEB_PUBLIC_URL + /`.

### Preview : client dédié `myagents-server-preview`

Keycloak n'accepte `*` qu'en dernier caractère (correspondance par préfixe). Pour les previews (VPN, dev), un client dédié avec un préfixe large évite d'enregistrer chaque PR. Ne jamais appliquer ce wildcard au client de prod ou de beta.

| Champ | Valeur |
|---|---|
| Client ID | `myagents-server-preview` (`OIDC_CLIENT_ID` des values preview) |
| Root URL | `https://myagents-pr-` (non utilisé, peut rester vide) |
| Home URL | vide |
| Valid redirect URIs | `https://myagents-pr-*` |
| Valid post logout redirect URIs | `https://myagents-pr-*` |
| Web origins | vide (le navigateur n'appelle jamais Keycloak, le serveur fait le flux code) |

Son secret (onglet Credentials) va dans `OIDC_CLIENT_SECRET` du Vault de la preview.

### Prod / beta : client `myagents-server`

URIs exactes de l'environnement, sans wildcard : `https://<host>/api/auth/callback` en redirect URI, `https://<host>/*` en post logout redirect URI.

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

## Policy Vault

Pour que le Vault Secrets Operator puisse lire ces secrets, une policy Vault est nécessaire :

```hcl
# Policy pour myagents-prod
path "kv/data/prod/myagents/*" {
  capabilities = ["read", "list"]
}

# Policy pour myagents-beta
path "kv/data/beta/myagents/*" {
  capabilities = ["read", "list"]
}

# Policy pour myagents-preview
path "kv/data/preview/myagents/*" {
  capabilities = ["read", "list"]
}
```

## Vérification des secrets dans Vault

```bash
# Lister les secrets d'un environnement
vault kv list kv/prod/myagents/

# Vérifier le contenu d'un secret (application)
vault kv get kv/prod/myagents/app

# Vérifier le contenu d'un secret (postgres)
vault kv get kv/prod/myagents/postgres
```

## Intégration avec Vault Secrets Operator

Une fois les secrets créés dans Vault, le Vault Secrets Operator :

1. Crée un Secret Kubernetes `myagents-secrets` à partir de `kv/<env>/myagents/app`
2. Crée un Secret Kubernetes `postgres-secret` à partir de `kv/<env>/myagents/postgres`
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
