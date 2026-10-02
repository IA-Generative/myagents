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

### Clés requises

- **`DATABASE_URL`** : URL PostgreSQL (`postgresql://...`, convertie en `postgresql+asyncpg://` par le serveur)
- **`OIDC_ISSUER`** : `https://<keycloak>/realms/myagents` (claim `iss` exact des tokens)
- **`OIDC_CLIENT_SECRET`** : secret du client Keycloak `myagents-server` (onglet Credentials)
- **`OPENAI_API_KEY`** : clé de l'endpoint LLM compatible OpenAI (Scaleway, OpenWebUI, etc.)
- **`OPENAI_BASE_URL`** et **`LLM_DEFAULT_MODEL`** : endpoint et modèle LLM (non secrets, gardés dans Vault)
- **`OPENWEBUI_API_KEY`** : secret partagé vérifié sur `/v1/*` ; à reporter dans la connexion OpenWebUI vers le serveur
- **`SESSION_SECRET`** : clé de chiffrement des jetons en base (repli sur `OIDC_CLIENT_SECRET` si absente)
- **`PRESENTATION_LINK_SECRET`** : signature des liens de téléchargement (repli sur `OPENWEBUI_API_KEY` si absente)

### Exemple de création (Vault CLI)

`vault kv put` écrase le secret entier ; utiliser `vault kv patch` pour ajouter des clés.

```bash
vault kv put kv/preview/myagents/app \
  DATABASE_URL='postgresql://user:pass@host:5432/db' \
  OIDC_CLIENT_SECRET='xxx' \
  OIDC_ISSUER='https://<keycloak>/realms/myagents' \
  OPENAI_BASE_URL='https://<endpoint-llm>/v1' \
  LLM_DEFAULT_MODEL='gpt-oss-120b' \
  OPENAI_API_KEY='xxx' \
  OPENWEBUI_API_KEY="$(openssl rand -hex 32)" \
  SESSION_SECRET="$(openssl rand -base64 32)" \
  PRESENTATION_LINK_SECRET="$(openssl rand -hex 32)"
```

Même chose pour `kv/prod/myagents/app` et `kv/beta/myagents/app`, avec des valeurs distinctes.

### Variables non secrètes (`app.env`, values privées)

À ne pas dupliquer dans Vault (`app.env` prime sur `envFrom`). `OIDC_ISSUER`, `OPENAI_BASE_URL` et `LLM_DEFAULT_MODEL` sont déjà dans Vault ci-dessus.

```yaml
ENVIRONMENT: preview            # "production" impose OIDC_ENABLED=true
OIDC_ENABLED: "true"
OIDC_INTERNAL_URL: http://<keycloak-svc>:8080/realms/myagents   # optionnel
OIDC_CLIENT_ID: myagents-server
OIDC_AUDIENCE: myagents-api     # doit figurer dans le claim aud, ou vide pour désactiver
WEB_PUBLIC_URL: https://myagents-pr-<n>.preview.mirai-hp.cpin.numerique-interieur.com
PUBLIC_BASE_URL: https://myagents-pr-<n>.preview.mirai-hp.cpin.numerique-interieur.com
CORS_ORIGINS: '["https://myagents-pr-<n>.preview.mirai-hp.cpin.numerique-interieur.com"]'
QDRANT_URL: http://qdrant:6333
```

## Client Keycloak `myagents-server`

Client confidentiel (Client authentication = On), flux Standard flow uniquement, PKCE `S256`.
Le serveur calcule `redirect_uri = WEB_PUBLIC_URL + /api/auth/callback` et `post_logout_redirect_uri = WEB_PUBLIC_URL + /`.

| Champ | Valeur (preview) |
|---|---|
| Root URL | `https://myagents-pr-*.preview.mirai-hp.cpin.numerique-interieur.com` |
| Home URL | `https://myagents-pr-*.preview.mirai-hp.cpin.numerique-interieur.com/` |
| Valid redirect URIs | `https://myagents-pr-*.preview.mirai-hp.cpin.numerique-interieur.com/api/auth/callback` |
| Valid post logout redirect URIs | `https://myagents-pr-*.preview.mirai-hp.cpin.numerique-interieur.com/*` |
| Web origins | vide (le navigateur n'appelle jamais Keycloak, le serveur fait le flux code) |

Remarques :

- Keycloak n'accepte le wildcard qu'en fin de chemin : il faut un client dédié par host exact, ou le wildcard sur le domaine si votre version l'autorise. Sinon, ajouter une URI par PR.
- Pour prod/beta, remplacer par le host exact de l'environnement (sans wildcard).
- Le client doit avoir le client scope `myagents-api` (audience) et `groups` en default scopes.

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
