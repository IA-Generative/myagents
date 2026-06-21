# AGENTS.md

Contexte pour assistants de code (Cursor, Copilot, etc.). Pieges
operationnels appris en incident, non derivables du code seul. **Pour la stack,
le setup et le demarrage local, voir [README.md](README.md)** — ce fichier
n'y revient pas.

## TL;DR

App Next.js 14 + Prisma + Postgres. Double cible : Docker compose (dev local,
via le socle `../owuicore-main/`) et K8s Scaleway (namespace `miraiku`,
`https://myagents.fake-domain.name`).

## Invariants a ne pas casser

### Schema DB — **jamais `prisma db push`** en prod

Le Job K8s [deploy/k8s/base/job-migrate.yaml](deploy/k8s/base/job-migrate.yaml) execute
`prisma migrate deploy`. Les migrations SQL sont versionnees dans
[prisma/migrations/](prisma/migrations/). Reecrire une migration existante ou
rebasculer sur `db push` reintroduit un bug qui corrompt silencieusement la DB
(un migrator avec un schema stale avait supprime une valeur d'enum vivante et
des tables entieres).

### Toute modif de `schema.prisma` → rebuild **les deux** images

Le runner embarque `@prisma/client` (genere au build), le migrator embarque
le CLI Prisma + `prisma/migrations/`. `./deploy/build-image.sh` build les deux,
`./deploy/push-image.sh` push les deux. Oublier le migrator laisse la DB
desynchronisee du code.

### `imagePullPolicy: Always` partout

Deployment ET Job migrate. On re-push souvent la meme balise `:dev` avec un
digest different ; `IfNotPresent` laisse le node reutiliser une ancienne image
cachee et reintroduit le bug ci-dessus.

### `OWUI_BASE_URL` : port different Docker vs K8s

- Docker compose : `http://openwebui:8080` (le container expose 8080)
- K8s : `http://openwebui` (port 80 — le Service `openwebui` mappe 80→8080)

**Ne pas fixer `OWUI_BASE_URL` dans `.env`** — `deploy/prepare-env.sh` applique
le defaut K8s correct, et compose a son propre defaut.

### `OWUI_ADMIN_API_KEY` obligatoire dans `agent-builder-secrets`

Sans cette cle, la creation d'agent tombe en fallback silencieux
("agent cree en base seulement") et le modele n'apparait jamais dans
OpenWebUI. A recuperer dans OWUI > Settings > Account > API Keys d'un compte
admin. Geree par `deploy/prepare-secrets.sh` si la variable est dans
l'environnement.

### Ingress nginx : buffer eleve pour NextAuth

[deploy/k8s/base/ingress.yaml](deploy/k8s/base/ingress.yaml) doit garder :
```
nginx.ingress.kubernetes.io/proxy-buffer-size: "16k"
nginx.ingress.kubernetes.io/proxy-buffers-number: "4"
```
Le defaut (4k) tronque les cookies NextAuth + Keycloak (state, PKCE, CSRF,
callback-url — tous chiffres) → `OAUTH_CALLBACK_ERROR state mismatch` au
login.

### `AGENT_BUILDER_IMAGE` : ne pas override dans `.env`

Laisser `prepare-env.sh` la deriver en `${REGISTRY}/miraiku-agents:${IMAGE_TAG}`.
Un override local sans prefix registry (ex: `miraiku-agents:dev`) casse
`push-image.sh`.

## Cascade `.env`

Shell > `./.env` > `../owuicore-main/.env`. Credentials partages (Scaleway,
Keycloak, Postgres, registry) restent dans le socle. Detail dans
[README.md](README.md).

## Workflow evolution du schema DB

```
1. editer prisma/schema.prisma
2. npx prisma migrate dev --name <description>   # genere + applique en local
3. git add prisma/migrations/<timestamp>_<desc>/
4. ./deploy/build-image.sh && ./deploy/push-image.sh
5. ./deploy/deploy-k8s.sh                        # run job migrate-deploy + rollout
```

## Diagnostic rapide

```bash
# Logs
kubectl -n miraiku logs deploy/agent-builder --tail=100 -f
kubectl -n miraiku logs job/agent-builder-migrate

# Etat DB agentbuilder
kubectl -n miraiku exec deploy/postgres -- psql -U app -d agentbuilder -c "\dt"
kubectl -n miraiku exec deploy/postgres -- \
  psql -U app -d agentbuilder -c 'SELECT unnest(enum_range(NULL::"Visibility"));'
kubectl -n miraiku exec deploy/postgres -- \
  psql -U app -d agentbuilder -c 'SELECT * FROM "_prisma_migrations";'

# OWUI (sqlite dans /app/backend/data/webui.db)
kubectl -n miraiku exec deploy/openwebui -- python3 -c "
import sqlite3
c=sqlite3.connect('/app/backend/data/webui.db')
for r in c.execute('SELECT id, email, role FROM user'): print(r)
"

# Tester un endpoint depuis le pod (pour contourner l'ingress/auth)
POD=$(kubectl -n miraiku get pod -l app=agent-builder -o jsonpath='{.items[0].metadata.name}')
IP=$(kubectl -n miraiku get pod "$POD" -o jsonpath='{.status.podIP}')
kubectl -n miraiku exec "$POD" -- node -e "
  require('http').get('http://$IP:3000/api/health', r => {
    let b=''; r.on('data',c=>b+=c); r.on('end',()=>console.log(r.statusCode, b));
  });
"
```

## References

- Spec fonctionnelle : [docs/specs/agent-builder-spec.md](docs/specs/agent-builder-spec.md)
- Socle Keycloak+OWUI+Postgres : `../owuicore-main/`
- Orchestrateur deploy : [deploy/deploy-k8s.sh](deploy/deploy-k8s.sh)
