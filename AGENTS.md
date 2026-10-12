# AGENTS.md

Contexte pour assistants de code. Pièges opérationnels appris en incident, non dérivables du
code seul. Stack, installation et démarrage local : [README.md](README.md).

## TL;DR

- `apps/server` (FastAPI, SQLAlchemy async, Alembic, LangChain) + `apps/web` (Vue 3, vue-dsfr) :
  **une seule image** (`Dockerfile` racine), le server sert la SPA. C'est l'application cible.
- `apps/next` : l'ancienne app Next.js + Prisma, encore en service sur la bêta
  (`mesagents.numerique-interieur.com`) jusqu'à la bascule. En dépréciation : correctifs de
  sécurité seulement.
- Déploiement : chart `helm/`, piloté par Argo CD. Les valeurs réelles (hôtes, secrets) vivent
  dans le dépôt privé `IA-Generative/mirai-apps-beta-private`, **jamais ici** (dépôt public).

## Invariants à ne pas casser

### Schéma : Alembic seulement, révisions jamais réécrites

Toute évolution passe par une nouvelle révision dans `apps/server/alembic/versions/`
(`make migration MSG=...`). Réécrire une révision déjà appliquée, ou créer les tables par
`Base.metadata.create_all` hors des tests, désynchronise silencieusement la base (incident
connu sur l'ancienne app avec `prisma db push`).

### La migration passe avant tout nouveau pod

Sous Argo CD, le Job `alembic upgrade head` est un hook Sync de vague 1 : après la base
(vague 0), avant le Deployment (vague 2). Ne pas le repasser en PostSync : de nouveaux pods
tourneraient sur l'ancien schéma.

### `imagePullPolicy: Always`

On republie des étiquettes stables (`pr-<n>`, `beta`). Avec `IfNotPresent`, un nœud relance
une image périmée en cache. Les previews forcent en plus le redémarrage par l'annotation
`preview/commit`.

### Sous-chart postgres : clés `postgres.auth.*`, mot de passe hors `lookup`

Le sous-chart cloudpirates lit `postgres.auth.{username,database,password,existingSecret}` ;
toute autre clé est ignorée sans erreur. Sans `existingSecret`, son mot de passe est tiré par
`lookup`, qu'Argo CD ne sait pas évaluer : il changerait à chaque synchronisation. Sous Argo CD,
toujours un `existingSecret`, et `DATABASE_URL` fournie par `app.envFromSecrets`.

### Variables LLM obligatoires, sans valeur par défaut

`OPENAI_BASE_URL`, `OPENAI_API_KEY`, `LLM_DEFAULT_MODEL`, `LLM_EMBEDDING_MODEL`,
`LLM_ASSIST_MODEL`, `LLM_ONBOARDING_MODEL` : le server refuse de démarrer sans elles. Ne pas
réintroduire de nom de modèle en dur dans le code : un modèle retiré du hub casse l'app sans
erreur visible (cas réel : `mistral-small-3.2-24b-instruct-2506`, retiré le 25/08). Préférer
les alias de la passerelle (`chat`, `chat-pro`, `vision`).

### Accès : SSO obligatoire en production, groupe exigé

- `ENVIRONMENT=production` refuse `OIDC_ENABLED=false`. Hors production, sans OIDC, l'en-tête
  `X-User-ID` est cru : ne jamais exposer un environnement OIDC désactivé.
- `OIDC_GROUPE_EXIGE` restreint l'accès à un groupe Keycloak (nom feuille, ou chemin s'il
  commence par `/`). Contrôlé au retour de connexion (aucune session créée) et à chaque
  requête. Vide = ouvert à tout le realm.

### Garde anti-injection sur tout appel au modèle

Toute route qui envoie du texte utilisateur au modèle passe par `app/llm/guard.py` (entrée,
system prompt durci, sortie + juge), y compris `/v1/chat/completions`. Une nouvelle route LLM
sans garde est une régression de sécurité.

## Capacités gouvernées (`/api/v2`, `/mcp`)

Mise en œuvre de l'ADR « Mes agents : un catalogue de capacités gouvernées, exposé par MCP ».
Le contrat servi est GÉNÉRÉ dans `docs/contrats/contrat-capacites-mirai.md`
(`python -m app.scripts.exporter_contrat`, contrôlé par `tests/test_contrat_doc.py`).

- Modèle : `capabilities` (fiche de travail), `capability_versions` (forme publiée, immuable :
  un écouteur ORM refuse toute mise à jour), `runs` (journal, jamais de contenu), `pins`,
  `suspended_clients` (`app/models/capability.py`). Les tables `agents*` restent en place ; la
  migration `d4e6f8a0b135` copie les agents en capacités (réversible).
- Identité : jeton Keycloak avec `aud` ∋ `mesagents`, `azp`, `scope` (`mesagents:read|act|author|
  review`) — `app/api/deps_v2.py`, table portée → opération dans `app/core/portees.py`. Sans SSO
  (dev), en-têtes `X-User-ID`, `X-User-Groups`, `X-User-Azp`, `X-User-Scopes`, `X-User-Roles`.
- Un seul chemin d'exécution (`app/services/execution.py`) pour `tools/call`, `executer_capacite`,
  `POST …/test` et les dépendances : seules les dépendances déclarées sont appelables, garde en
  entrée et en sortie, UNE ligne de journal par appel (`mesagents.journal` + table `runs`).
- `tools/list` = trois méta-outils + capacités épinglées (≤ `MESAGENTS_EPINGLES_MAX`), filtrées
  par visibilité et par contexte de surface (`MESAGENTS_CONTEXTES_AZP`). Jamais le catalogue.
- Garde de définition à la publication (`app/llm/guard/definition.py`, `ruleset_version`) ;
  re-vérification de masse par `POST /api/v2/admin/guard/recheck`.
- Conformité C-A1…C-A12 : `make conformite` (Docker Compose : Keycloak de test, fausse MirAI API,
  faux serveur MCP de dépendance) ; rejeu contre une preview : `BASE_URL=… JETONS_DIR=… uv run
  pytest tests/conformite`.

## Version de l'image (`/__version__`, ADR-0004)

L'image écrit `/app/version.json` à sa construction (`scripts/version_json.py`, copié tel quel
depuis la skill `repo-version-json` — ne pas l'adapter) et le sert sur `GET /__version__` :
public, hors OpenAPI, hors journaux. Les cinq build-args (`VERSION`, `COMMIT`, `BUILD`,
`CODE_DATE`, `SOURCE`) sont passés par `ci.yml` (`pr-<n>`), `branches.yml` (`beta-<sha8>`, qui
vérifie que l'image dit le commit fusionné) et `cd.yml` (`X.Y.Z`). Un build de poste donne
`version: "dev"`. La route doit rester déclarée **avant** le catch-all de la SPA, sinon
`/__version__` rend `index.html` en 200.

## Previews

Une PR étiquetée `beta-preview` est construite (`mes-agents:pr-<n>`) et déployée par l'Argo CD
d'internal-gw sur `https://myagents-pr-<n>.beta-preview.numerique-interieur.com`, avec sa propre
base. ApplicationSet et secrets : `mirai-apps-beta-private/apps/argocd/`.

```bash
kubectl -n argocd get applications -l preview/depot=myagents
kubectl -n preview-myagents-<n> get pods,jobs
kubectl -n preview-myagents-<n> logs deploy/mes-agents --tail=100 -f
kubectl -n preview-myagents-<n> logs job/mes-agents-migrate
```

## Tests

```bash
cp .env.test.example apps/server/.env   # variables LLM factices
make check                              # ruff, pytest, eslint, vue-tsc, vitest
```
