# MirAI Agent Builder

Application Next.js 14 permettant aux agents du ministère de l'Intérieur de
créer et partager des agents IA sans jamais ouvrir l'interface admin
d'OpenWebUI. Spec complète dans [docs/specs/agent-builder-spec.md](docs/specs/agent-builder-spec.md).

> **État actuel** : scaffold. Le squelette compile et se déploie (Docker +
> Kubernetes Scaleway), l'authentification Keycloak est câblée, le wizard de
> création d'agent est navigable, le BFF relaie déjà l'endpoint
> `/api/ab/prompt/assist` vers OpenWebUI. Les fonctionnalités métier (catalogue,
> connecteurs SI, index mail, versioning) sont des coquilles à implémenter dans
> les itérations MVP / V1 / V2 (voir §8 du prompt).

## Stack

- **Framework** : Next.js 14 (App Router) + React 18 + TypeScript
- **Design system** : DSFR officiel (`@codegouvfr/react-dsfr`)
- **Auth** : NextAuth 4 + Keycloak (realm `openwebui` du socle owuicore-main)
- **DB** : PostgreSQL (partagée avec le socle, base `agentbuilder`) + Prisma
- **BFF** : routes Next.js côté serveur, wrapper `src/lib/owui-client.ts`
- **Conteneur** : Docker multi-stage (Node 20 alpine, Next.js standalone)
- **Déploiement** : Kubernetes Scaleway, namespace `miraiku`, ingress nginx +
  cert-manager letsencrypt-prod, URL `https://myagents.fake-domain.name`

## Pré-requis

Le socle [owuicore-main](../owuicore-main/) doit être déployé **avant** :
- En local : `docker compose up -d` dans `owuicore-main` crée le réseau
  `owui-net` auquel ce compose se rattache.
- En K8s : le socle fournit Keycloak, OpenWebUI, PostgreSQL et le cert-manager.

## Configuration — `.env` en cascade

**Règle** : les credentials Scaleway (registry, LLM), Keycloak et PostgreSQL
restent dans `../owuicore-main/.env`. Notre `./.env` ne contient que ce qui
est **spécifique à l'Agent Builder** (image, host, NEXTAUTH_SECRET,
DATABASE_URL propre à la base `agentbuilder`).

[deploy/prepare-env.sh](deploy/prepare-env.sh) charge en cascade (première
valeur rencontrée gagne) :

1. variables shell déjà exportées (CI, override ponctuel)
2. `./.env` (overrides Agent Builder)
3. `../owuicore-main/.env` (credentials partagés du socle)

La fonction `load_dotenv_preserve_existing` (copiée depuis le socle dans
[deploy/scripts/load_env.sh](deploy/scripts/load_env.sh)) n'écrase jamais une variable
déjà définie — d'où l'ordre « overrides d'abord, défauts ensuite ».

Pour pointer vers un autre emplacement du `.env` du socle :
```bash
OWUICORE_ENV_FILE=/autre/chemin/.env ./deploy/deploy-k8s.sh
```

Variables requises côté Agent Builder uniquement (à mettre dans `./.env`) :
- `AGENT_BUILDER_IMAGE` (ou laissé dérivé de `${REGISTRY}/miraiku-agents:${IMAGE_TAG}`)
- `AGENTS_HOST` (défaut : `myagents.fake-domain.name`)
- `NEXTAUTH_SECRET` (générer avec `openssl rand -base64 32`)
- `DATABASE_URL` (pointant vers la base `agentbuilder` du Postgres du socle)

Tout le reste (`REGISTRY_SERVER`, `REGISTRY_PASSWORD`, `KEYCLOAK_CLIENT_SECRET`,
`KEYCLOAK_HOST`, `LETSENCRYPT_EMAIL`, `NAMESPACE`...) est hérité du socle.

## Démarrage local

```bash
# 1. Configurer l'environnement (minimal — le reste est hérité du socle)
cp .env.example .env
# → renseigner NEXTAUTH_SECRET et DATABASE_URL au minimum.
# KEYCLOAK_CLIENT_SECRET, REGISTRY_*, LETSENCRYPT_EMAIL : déjà dans
# ../owuicore-main/.env, rien à recopier.

# 2. Créer la base agentbuilder sur le Postgres du socle (une seule fois)
docker exec -it owuicore-main-postgres-1 \
  psql -U owui -c "CREATE DATABASE agentbuilder; GRANT ALL ON DATABASE agentbuilder TO app;"

# 3. Lancer
docker compose up -d --build
curl -fsS http://localhost:3001/api/health
# → {"status":"ok","service":"miraiku-agents"}
```

Ouvrir http://localhost:3001 → redirection vers `/sign-in` → SSO Keycloak →
`/agents`.

## Déploiement Kubernetes Scaleway

```bash
# 1. Créer la base agentbuilder sur le Postgres du socle
kubectl -n miraiku exec deploy/postgres -- \
  psql -U owui -c "CREATE DATABASE agentbuilder; GRANT ALL ON DATABASE agentbuilder TO app;"

# 2. Importer le client Keycloak (voir deploy/keycloak/README.md)

# 3. Configurer .env avec les valeurs prod (KEYCLOAK_CLIENT_SECRET, DATABASE_URL, ...)

# 4. Déployer
./deploy/deploy-k8s.sh
# → build image → push registry Scaleway → apply manifestes → wait rollout

# 5. Vérifier
curl -fsS https://myagents.fake-domain.name/api/health
kubectl -n miraiku get pods,svc,ingress -l app=agent-builder
kubectl -n miraiku logs deploy/agent-builder --tail=50
```

## Structure du dépôt

```
.
├── app/                    Next.js App Router — pages + API BFF
│   ├── agents/new/         Wizard de création (4 étapes DSFR)
│   ├── api/ab/             Endpoints BFF (§6 de la spec)
│   └── api/auth/           NextAuth / Keycloak
├── src/
│   ├── lib/                Adaptateurs : env, auth, prisma, clients OWUI/Scaleway, prompt-guard
│   ├── packages/           Modules isolés réutilisables (prompt-guard : cœur sans dépendance)
│   └── types/              Augmentations de types (NextAuth)
├── prisma/                 schema.prisma (tables ab_*) + migrations
├── tests/redteam/          Suite red-team / prompt-injection (opt-in, voir le README local)
├── deploy/                 Tout le déploiement au même endroit :
│   ├── *.sh                Scripts build / push / deploy
│   ├── scripts/            helper load_env.sh (cascade .env)
│   ├── k8s/base/           Manifestes templates (rendus via envsubst)
│   └── keycloak/           Client OIDC à importer dans le realm openwebui
├── public/                 Assets statiques
├── docs/                   📚 Toute la documentation — voir docs/README.md
│   ├── specs/              Spec produit + roadmap V2
│   └── mockups/            Maquettes DSFR (HTML + PNG)
├── Dockerfile  docker-compose.yml
└── README.md  AGENTS.md    Ce fichier · contexte pour les assistants de code
```

Toute la documentation vit sous [docs/](docs/) (point d'entrée : [docs/README.md](docs/README.md)).

## Tests de bout en bout

Une fois déployé, smoke-test du BFF :

```bash
# Sans session → 401
curl -i https://myagents.fake-domain.name/api/ab/prompt/assist

# Avec session (après login navigateur), le bouton "Aide-moi à écrire" de
# l'étape 2 du wizard déclenche POST /api/ab/prompt/assist qui proxie
# OpenWebUI /api/chat/completions. C'est le test d'intégration BFF → OWUI.
```

## Ce qui **n'est pas** livré par ce scaffold

- Catalogue communautaire, ratings, fork, versioning (→ V1, §3.2/3.6)
- Connecteurs SI (LDAP, Tchap, GED, SIRH, MCP, MyVault, RPA) (→ V2, §3.4)
- Index mail (→ V2, §3.5)
- Upload de documents → knowledge bases OpenWebUI (→ MVP, §3.1 étape 3)
- Prévisualisation live du chat (→ MVP, §3.1 étape 4)
- Pipeline CI/CD (→ à définir selon l'équipe socle)

Roadmap détaillée dans le §8 de [docs/specs/agent-builder-spec.md](docs/specs/agent-builder-spec.md).
