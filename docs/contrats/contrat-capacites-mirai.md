# Contrat de capacités MirAI — version 2

> Document GÉNÉRÉ depuis le code de Mes agents (`python -m app.scripts.exporter_contrat`) ;
> toute modification manuelle est écrasée. Référence : ADR « Mes agents : un catalogue de
> capacités gouvernées, exposé par MCP ». Remplace le contrat d'agents V1 (compatibilité OpenAI
> non conservée).

## Principe

Une **capacité** est un prompt métier, un outil externe (serveur MCP, API HTTP) ou leur
composition. Le fournisseur (Mes agents) la catalogue, la vérifie à la publication (garde), la
sert à ceux qui ont le droit de l'appeler et journalise chaque exécution. Une version publiée est
immuable et hachée ; `tools/list` ne sert jamais le catalogue complet : trois méta-outils et les
capacités épinglées par la personne (au plus `MESAGENTS_EPINGLES_MAX`).

## Conventions communes

- Transport : HTTPS ; MCP en Streamable HTTP sur `POST /mcp` (et `GET /mcp` pour les
  notifications) ; API de cycle de vie en REST JSON sous `/api/v2/`.
- Authentification : `Authorization: Bearer <jeton d'accès Keycloak de la personne>`. Le
  fournisseur vérifie signature (JWKS), émetteur, expiration, `aud` contenant `mesagents`, et lit
  `sub`, `groups` (chemins complets), `azp`, `scope`. Un consommateur n'envoie jamais de droit dans
  le corps ; les champs `published_by`, `published_from`, `hash`, `version` envoyés sont ignorés.
- En-têtes : toutes les réponses des routes du contrat portent `Cache-Control: no-store` et
  `Vary: Origin`. CORS limité aux origines configurées (`CONTRAT_ORIGINES`, motifs), préflight
  `OPTIONS` avec `Access-Control-Allow-Headers: Authorization, Content-Type`, sans
  `Allow-Credentials`.
- Identifiants : `name` est un slug stable `[a-z0-9][a-z0-9._-]{2,63}` ; une version est un entier
  croissant ; `hash` est le `sha256` hexadécimal de la sérialisation canonique (JSON trié, UTF-8,
  sans espaces) de `definition + input_schema + dependencies`.
- Découverte OAuth 2.1 : `GET /.well-known/oauth-protected-resource` (RFC 9728) ; un `401` porte
  `WWW-Authenticate: Bearer resource_metadata="…/.well-known/oauth-protected-resource/mcp"`.

## Cycle de vie

Brouillon → (test) → publication (`maturity` `alpha` | `beta` | `general`, `visibility`) → version
immuable → retrait. `PATCH` sur une capacité publiée répond `409 immutable_version` ; `POST
…/draft` ouvre un brouillon pendant que la version publiée reste servie ; la publication suivante
crée la version n+1. `publish` applique dans l'ordre : droit de la personne, portée du client,
verdict de garde (`422 guard_rejected` + `details[]`), règle de dépendance (publiée, visible,
version épinglée, maturité au moins égale : `422 dependency_not_allowed`), puis crée la version et
son `hash`. Une capacité `grounding: open` se publie avec au moins trois exemples. La visibilité
`ministry` et toute capacité non lecture seule passent par une revue (`status: submitted` jusqu'à
la publication par un porteur de `mesagents:review` et du rôle `mesagents-reviewer`). `retire`
suspend les dépendants (`status: suspended`) et émet `notifications/tools/list_changed`.

Visibilité : l'auteur voit tout ; les autres voient une capacité servie `ministry` (tout le
ministère) ou `community` (membres du groupe `community_path`) ; `alpha` n'est visible que de
l'auteur et de son groupe ; `beta` est servie marquée.

## Portées client (claim `scope`)

Une portée dit ce que l'application appelante PEUT demander ; les droits de la personne (visibilité, groupes, rôle) disent ce qu'elle peut obtenir. L'intersection fait foi.

| Portée | Ce qu'elle permet |
|---|---|
| `mesagents:read` | `tools/list`, `prompts/*`, `GET /api/v2/capabilities`, recherche et description |
| `mesagents:read` | `tools/call` et `executer_capacite` sur une capacité `readOnlyHint: true` |
| `mesagents:act` | `tools/call` et `executer_capacite` sur une capacité `readOnlyHint: false` (confirmation par la surface) |
| `mesagents:author` | créer, modifier, tester, publier en `private` / `community` (lecture seule), retirer ses propres capacités, épingler |
| `mesagents:review` | publier en `ministry` ou une capacité non lecture seule, retirer la capacité d'un autre, administration (export, re-vérification, clients suspendus) — avec le rôle `mesagents-reviewer` |
| `mesagents:delegate` | déclarée, toujours refusée (régime délégué hors V2) |

Un jeton portant `mesagents:delegate` est refusé (`403 forbidden`). Un client (`azp`) suspendu est refusé sur toutes les routes (`403 forbidden`), jeton valide ou non.

## API REST (`/api/v2`) et métadonnées

| Route | Résumé | Détail |
|---|---|---|
| `GET /.well-known/oauth-protected-resource` | Métadonnées OAuth de la ressource protégée |  |
| `GET /.well-known/oauth-protected-resource/mcp` | Métadonnées OAuth du point d'accès MCP |  |
| `POST /api/v2/admin/guard/recheck` | Re-vérifier toutes les versions servies (règle 7) | Rejoue la garde de définition ; une version non conforme est retirée et ses dépendants suspendus. |
| `GET /api/v2/admin/runs` | Export du journal | JSON Lines de toutes les exécutions (jamais de contenu). |
| `GET /api/v2/admin/suspended-clients` | Clients suspendus |  |
| `PUT /api/v2/admin/suspended-clients/{azp}` | Suspendre un client (azp) | Effet immédiat sur tous ses appels, jeton valide ou non. |
| `DELETE /api/v2/admin/suspended-clients/{azp}` | Lever la suspension |  |
| `GET /api/v2/capabilities` | Lister les capacités visibles (même forme que tools/list) | Les capacités que la personne peut voir : les siennes (brouillons compris) et celles servies pour elle. |
| `POST /api/v2/capabilities` | Créer un brouillon | `kind`, `definition`, schémas, dépendances, `grounding`, visibilité, exemples. Les champs posés par le service sont ignorés. |
| `GET /api/v2/capabilities/{cap_id}` | Lire une capacité | Fiche, versions et provenance ; la définition n'est rendue qu'à l'auteur et aux relecteurs. |
| `PATCH /api/v2/capabilities/{cap_id}` | Modifier un brouillon | Brouillon seulement : une capacité publiée répond `409 immutable_version` (ouvrez un brouillon). |
| `POST /api/v2/capabilities/{cap_id}/draft` | Ouvrir un brouillon sur une capacité publiée | La version publiée reste servie ; la publication suivante créera la version n+1. |
| `POST /api/v2/capabilities/{cap_id}/publish` | Publier | Ordre : droit de la personne, portée du client, verdict de garde, règle de dépendance, puis version + hash. `ministry` ou non lecture seule : revue. |
| `POST /api/v2/capabilities/{cap_id}/retire` | Retirer | Retire la version servie ; les capacités qui en dépendent passent à `suspended` et sont notifiées. |
| `GET /api/v2/capabilities/{cap_id}/runs` | Journal des exécutions | JSON Lines : une ligne par appel (ts, capability, version, hash, sub, azp, scope_used, guard_in, guard_out, duration_ms, status). Auteur, ou relecteur. |
| `POST /api/v2/capabilities/{cap_id}/test` | Tester le brouillon | Exécute le brouillon pour l'auteur et rend le résultat ET le verdict de garde sur la définition. |
| `GET /api/v2/pins` | Mes capacités épinglées |  |
| `PUT /api/v2/pins/{name}` | Épingler | Au plus `max` capacités ; au-delà, `422 invalid_request`. |
| `DELETE /api/v2/pins/{name}` | Désépingler |  |

### Corps de création (`POST /api/v2/capabilities`)

```json
{
  "properties": {
    "annotations": {
      "anyOf": [
        {
          "$ref": "#/components/schemas/Annotations"
        },
        {
          "type": "null"
        }
      ]
    },
    "community_path": {
      "anyOf": [
        {
          "maxLength": 255,
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Community Path"
    },
    "definition": {
      "additionalProperties": true,
      "title": "Definition",
      "type": "object"
    },
    "dependencies": {
      "items": {
        "$ref": "#/components/schemas/Dependency"
      },
      "maxItems": 20,
      "title": "Dependencies",
      "type": "array"
    },
    "description": {
      "default": "",
      "maxLength": 2000,
      "title": "Description",
      "type": "string"
    },
    "examples": {
      "items": {
        "$ref": "#/components/schemas/Example"
      },
      "maxItems": 20,
      "title": "Examples",
      "type": "array"
    },
    "grounding": {
      "default": "input",
      "enum": [
        "input",
        "open"
      ],
      "title": "Grounding",
      "type": "string"
    },
    "input_schema": {
      "additionalProperties": true,
      "title": "Input Schema",
      "type": "object"
    },
    "kind": {
      "enum": [
        "prompt",
        "mcp",
        "http"
      ],
      "title": "Kind",
      "type": "string"
    },
    "name": {
      "pattern": "^[a-z0-9][a-z0-9._-]{2,63}$",
      "title": "Name",
      "type": "string"
    },
    "output_schema": {
      "anyOf": [
        {
          "additionalProperties": true,
          "type": "object"
        },
        {
          "type": "null"
        }
      ],
      "title": "Output Schema"
    },
    "run_as": {
      "const": "user",
      "default": "user",
      "title": "Run As",
      "type": "string"
    },
    "title": {
      "maxLength": 200,
      "minLength": 1,
      "title": "Title",
      "type": "string"
    },
    "visibility": {
      "default": "private",
      "enum": [
        "private",
        "community",
        "ministry"
      ],
      "title": "Visibility",
      "type": "string"
    }
  },
  "required": [
    "name",
    "kind",
    "title",
    "definition"
  ],
  "title": "CapabilityCreate",
  "type": "object"
}
```

## Serveur MCP (`/mcp`)

Versions de protocole parlées : `2024-11-05`, `2025-03-26`, `2025-06-18`, `2025-11-25` (défaut `2025-06-18`). `Mcp-Session-Id` émis à l'initialisation, serveur sans état. `GET /mcp` (`Accept: text/event-stream`) transporte `notifications/tools/list_changed`.

| Méthode | Effet |
|---|---|
| `initialize` | Négociation de version et annonce des capacités du serveur (tools, prompts, list_changed). |
| `ping` | Vie du serveur. |
| `tools/list` | Trois méta-outils + les capacités épinglées (≤ plafond), filtrées par visibilité et par `azp`. |
| `tools/call` | Exécution sous l'identité ; méta-outils et capacités épinglées passent par le même chemin. |
| `prompts/list` | Une amorce par capacité `prompt` visible et servie (ses exemples) ; sans pagination. |
| `prompts/get` | L'amorce rendue : les arguments donnés, sinon le premier exemple de la version servie. |
| `notifications/initialized` | Notification du client ; réponse `202` sans corps. |

### Méta-outils (toujours présents dans `tools/list`)

#### `rechercher_capacites`

Cherche dans le catalogue des capacités accessibles à la personne (texte libre : ce qu'il faut faire). Renvoie au plus dix capacités (nom, titre, description courte, maturité). Appelle ensuite executer_capacite avec le nom retenu.

```json
{
  "type": "object",
  "properties": {
    "query": {
      "type": "string",
      "description": "Ce qu'il faut faire, en langage naturel",
      "maxLength": 200
    },
    "limit": {
      "type": "integer",
      "minimum": 1,
      "maximum": 10,
      "default": 10
    }
  },
  "required": [
    "query"
  ]
}
```

#### `decrire_capacite`

Le schéma complet (arguments attendus, annotations, version) d'une capacité nommée.

```json
{
  "type": "object",
  "properties": {
    "name": {
      "type": "string",
      "description": "Nom de la capacité"
    },
    "version": {
      "type": "integer",
      "minimum": 1
    }
  },
  "required": [
    "name"
  ]
}
```

#### `executer_capacite`

Exécute une capacité du catalogue sous l'identité de la personne : nom, version (facultative), arguments conformes à son schéma. Les refus sont rendus en erreur lisible.

```json
{
  "type": "object",
  "properties": {
    "name": {
      "type": "string",
      "description": "Nom de la capacité"
    },
    "version": {
      "type": "integer",
      "minimum": 1
    },
    "arguments": {
      "type": "object",
      "description": "Arguments conformes au schéma de la capacité"
    }
  },
  "required": [
    "name",
    "arguments"
  ]
}
```

### Forme d'un outil servi

`name`, `title`, `description` (préfixée `[bêta] ` pour une version `beta`), `inputSchema` (JSON Schema de la version servie), `annotations` (`readOnlyHint`, `destructiveHint`, `idempotentHint`, `openWorldHint`), `_meta` (`hash`, `version`, `maturity`, `grounding`). Résultat de `tools/call` : `content[]`, `isError`, `_meta` (`hash`, `version`, `maturity`, `generated` = `grounding: open`, `error` sur refus), `structuredContent` quand il y a lieu.

## Erreurs

REST : `{"error": {"code": "...", "message": "..."[, "details": [...]]}}` ; `message` est affichable tel quel ; `scope_missing` nomme la portée manquante ; `not_found` ne distingue jamais « n'existe pas » de « pas pour vous ».

| Statut | Code | Message par défaut |
|---|---|---|
| 400 | `invalid_request` | Requête invalide. |
| 401 | `invalid_token` | Jeton absent ou invalide. |
| 403 | `audience_mismatch` | Ce jeton n'est pas destiné à Mes agents. |
| 403 | `scope_missing` | Portée manquante. |
| 403 | `forbidden` | Accès refusé. |
| 404 | `not_found` | Capacité introuvable. |
| 409 | `immutable_version` | Une version publiée ne se modifie pas : ouvrez un brouillon. |
| 422 | `guard_rejected` | La garde a refusé la définition. |
| 422 | `dependency_not_allowed` | Une dépendance déclarée n'est pas admise. |
| 429 | `rate_limited` | Trop d'appels : réessayez plus tard. |
| 502 | `upstream_unavailable` | La capacité ne répond pas. |

MCP : codes JSON-RPC standard pour le protocole ; un refus de garde ou de droit est un RÉSULTAT d'outil `isError: true`, `_meta.error = {code, message}`, mêmes codes, plus `blocked_input`, `blocked_output` à l'exécution.

## Journal

Une ligne JSON par appel (logger `mesagents.journal`, table `runs`), exportable en JSON Lines par `GET /api/v2/capabilities/{id}/runs` (auteur, relecteur) et `GET /api/v2/admin/runs`. Jamais le contenu.

Champs : `ts`, `capability`, `version`, `hash`, `sub`, `azp`, `scope_used`, `guard_in`, `guard_out`, `duration_ms`, `status`, `run_id`, `parent_run_id`, `route`, `ruleset_version`, `capability_id`.
