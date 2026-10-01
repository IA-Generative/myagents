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
- **Auth** : NextAuth 4, stub "utilisateur local" en dev standalone (voir `apps/next/src/lib/auth.ts`)
- **DB** : PostgreSQL (conteneur local dédié, base `agentbuilder`) + Prisma
- **BFF** : routes Next.js côté serveur, wrapper `apps/next/src/lib/owui-client.ts`
- **Package manager** : Bun (`apps/next/package.json`, `apps/next/bun.lock`)
- **Conteneur** : Docker multi-stage (Bun alpine, Next.js standalone), contexte = `apps/next/`
- **Déploiement** : Kubernetes Scaleway, namespace `miraiku`, ingress nginx +
  cert-manager letsencrypt-prod, URL `https://myagents.fake-domain.name`

## Pré-requis

Aucun : l'application tourne en standalone, `docker-compose.yml` lance son
propre conteneur PostgreSQL (pas de dépendance à un socle externe type
`owuicore-main`).

## Configuration — `.env`

`./.env` contient uniquement les variables nécessaires en local :
- `AGENT_BUILDER_IMAGE`
- `AGENTS_HOST` (utilisé seulement pour le déploiement K8s)
- `NEXTAUTH_URL` (`http://localhost:3001` en local)
- `NEXTAUTH_SECRET` (générer avec `openssl rand -base64 32`)
- `DATABASE_URL` (pointe vers le service `postgres` du compose)

Les variables Scaleway (`SCW_LLM_BASE_URL`, `SCW_SECRET_KEY_LLM`) et
`OWUI_PUBLIC_URL` sont optionnelles (voir `.env.example`).

## Démarrage local

```bash
# 1. Configurer l'environnement
cp .env.example .env
# → NEXTAUTH_SECRET est généré automatiquement au premier lancement si absent.

# 2. Lancer (Postgres + migration Prisma + app, tout est inclus)
docker compose up -d --build
curl -fsS http://localhost:3001/api/health
# → {"status":"ok","service":"miraiku-agents"}
```

Ouvrir http://localhost:3001 → `/sign-in` → bouton "Continuer" (connexion
locale automatique, pas de SSO) → `/agents`.

## OpenWebUI local

Instance OpenWebUI optionnelle (profil compose `owui`) qui affiche les agents du
`server` FastAPI (`/v1`) et reçoit les modèles poussés par `apps/next`.

Raccourci : `make bootstrap` crée `.env` (clés générées), lance la stack + Keycloak + OpenWebUI,
applique les migrations et le seed. `make reset` supprime d'abord les volumes.
Détail des étapes :

```bash
# 1. Racine : générer la clé partagée server <-> OpenWebUI dans .env
cp -n .env.example .env
#    OPENWEBUI_API_KEY=$(openssl rand -hex 32)
#    OPENWEBUI_WEBUI_SECRET_KEY=$(openssl rand -hex 32)

# 2. Lancer la stack + OpenWebUI (crée le réseau partagé `myagents-shared`)
make up-owui
# → http://localhost:3000 : créer le compte admin (1er inscrit), les agents
#   apparaissent comme modèles (connexion http://server:8000/v1 auto-configurée).

# 3. apps/next (optionnel) : Paramètres > Compte > Clés API dans OpenWebUI, puis
#    dans apps/next/.env : OWUI_ADMIN_API_KEY=sk-...  (OWUI_BASE_URL=http://openwebui:8080 par défaut)
cd apps/next && docker compose up -d --force-recreate agent-builder
```

`make down` arrête aussi OpenWebUI ; `make clean` supprime ses données.

## SSO Keycloak local

Keycloak (realm `myagents`) fournit un SSO partagé entre `apps/web`, `apps/next`
et OpenWebUI. Le realm est importé au démarrage depuis
[`keycloak/realm-myagents.json`](keycloak/realm-myagents.json) :

- **Utilisateurs** : `admin` (rôle `admin`) et `user1` (rôle `user`). Leurs mots de passe sont
  `KEYCLOAK_DEV_ADMIN_PASSWORD` et `KEYCLOAK_DEV_USER_PASSWORD` dans `.env` (générés par `make ensure-env`)
- **Clients** : `myagents-web` (Vue, public PKCE), `miraiku-agents` (Next.js, confidentiel), `open-webui` (OWUI, confidentiel)
- **Mappers** : `myagents-api` (audience pour le server FastAPI), `groups` (claim `groups`, `full.path=false`)

```bash
# Racine : lance la stack + Keycloak + OpenWebUI (profils `sso` + `owui`)
make up-sso
# → Keycloak   http://localhost:8180  (console /admin : compte `admin`, mot de passe KEYCLOAK_ADMIN_PASSWORD)
# → OpenWebUI  http://localhost:3000  (SSO "Keycloak" : `admin` ou `user1`)
# → Server     http://localhost:8000  (OIDC_ENABLED=true, valide les Bearer JWT)
# → Web        http://localhost:5173  (redirige vers Keycloak si non authentifié)
```

`make bootstrap` lance aussi le SSO complet (Keycloak + OpenWebUI). Pour activer
la validation JWT côté server hors Docker, poser `OIDC_ENABLED=true` dans `.env`.

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
├── apps/
│   └── next/               Application Next.js — 100% indépendante (deps, lockfile, Dockerfile)
│       ├── app/            Next.js App Router — pages + API BFF
│       │   ├── agents/new/ Wizard de création (4 étapes DSFR)
│       │   ├── api/ab/     Endpoints BFF (§6 de la spec)
│       │   └── api/auth/   NextAuth / Keycloak
│       ├── src/
│       │   ├── lib/        Adaptateurs : env, auth, prisma, clients OWUI/Scaleway, prompt-guard
│       │   ├── packages/   Modules isolés réutilisables (prompt-guard : cœur sans dépendance)
│       │   └── types/      Augmentations de types (NextAuth)
│       ├── prisma/         schema.prisma (tables ab_*) + migrations
│       ├── tests/redteam/  Suite red-team / prompt-injection (opt-in, voir le README local)
│       ├── public/         Assets statiques
│       ├── package.json  bun.lock
│       └── Dockerfile      Contexte de build = apps/next/
├── deploy/                 Tout le déploiement au même endroit :
│   ├── *.sh                Scripts build / push / deploy (référencent apps/next/Dockerfile)
│   ├── scripts/            helper load_env.sh (cascade .env)
│   ├── k8s/base/           Manifestes templates (rendus via envsubst)
│   └── keycloak/           Client OIDC à importer dans le realm openwebui
├── docs/                   📚 Toute la documentation — voir docs/README.md
│   ├── specs/              Spec produit + roadmap V2
│   └── mockups/            Maquettes DSFR (HTML + PNG)
├── docker-compose.yml      Contexte de build : apps/next
├── Makefile                Cibles délèguent à `cd apps/next && bun ...`
└── README.md  AGENTS.md    Ce fichier · contexte pour les assistants de code
```

Chaque application sous `apps/` est indépendante en dépendances (son propre
`package.json` + lockfile Bun + Dockerfile). D'autres apps pourront être
ajoutées sous `apps/<nom>/` sans impacter `apps/next/`.

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
