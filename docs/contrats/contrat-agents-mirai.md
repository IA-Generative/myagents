# Contrat d'agents MirAI

Ce contrat dit comment une application ou un plug-in **liste les agents auxquels une personne a
droit** et **les lance sur ce qu'elle a sous les yeux**. Il est servi par Mes agents et consommé
par Mon portail, Mes réunions, Mes collections et les plug-ins bureautiques. Il est le jumeau du
contrat de recherche MirAI (`mysearch/docs/contrat-recherche-mirai.md`) : même jeton, même façon
d'ajouter une audience, mêmes erreurs, même CORS.

Version 1, 2026-10-06. Servie par la branche `beta` de Mes agents à partir de la PR qui porte ce
fichier.

## Principe

- **Un agent est un modèle.** Lancer un agent, c'est `POST /v1/chat/completions` avec
  l'identifiant de l'agent dans `model`. Toute surface qui sait choisir un modèle sait choisir un
  agent.
- **Les droits sont appliqués par Mes agents**, depuis l'identité du jeton (`sub`, `groups`). Un
  consommateur ne reçoit jamais un agent qu'il n'aurait pas le droit de lancer, et ne déduit
  jamais un droit d'un paramètre client.
- **Le contenu des fiches est une donnée non fiable** : texte brut, tailles bornées. Un
  consommateur l'affiche par `textContent`, jamais comme du HTML.
- **Le prompt système de l'agent fait foi.** Un message `system` envoyé par le consommateur est
  ignoré. La garde anti-injection de Mes agents s'applique à l'entrée et à la sortie.

## Authentification et CORS

- `Authorization: Bearer <jeton>`. Le jeton est le jeton d'accès Keycloak de la personne, émis
  pour le client public du consommateur (`mysearch`, `mycollections-front`…) ou pour un client
  confidentiel qui le relaie (`mes-reunions`).
- Mes agents vérifie la signature (JWKS), l'émetteur, l'expiration, **son audience `mesagents`
  dans `aud`**, et, si une liste est configurée, `azp` parmi les clients autorisés. L'audience
  est ajoutée par une portée optionnelle `mesagents-agents` du client appelant (voir
  `keycloak/`). Ne jamais configurer `audience=<client appelant>` : ce serait une confusion
  d'audience.
- Le claim `groups` doit porter les **chemins complets** (`/g/…`) : la même portée les ajoute.
  Un nom feuille est accepté pour une communauté déclarée par un nom feuille, jamais pour un
  chemin.
- CORS limité aux routes du contrat. Les origines autorisées sont lues dans
  `CONTRAT_ORIGINES` (motifs `fnmatch` acceptés : `https://mysearch-pr-*.exemple`). Le service
  répond au préflight `OPTIONS` avec `Access-Control-Allow-Headers: Authorization, Content-Type`
  et `Vary: Origin`, sans `Allow-Credentials`.
- Toutes les réponses du contrat portent `Cache-Control: no-store`. Rien du contenu n'est
  journalisé en clair.
- **Extensions de navigateur** (Firefox, Chrome) : une extension qui déclare l'hôte de Mes agents
  dans ses permissions d'hôte n'est pas soumise au CORS ; son origine (`moz-extension://…`,
  `chrome-extension://…`) n'a pas à figurer dans `CONTRAT_ORIGINES`. Un plug-in bureautique
  (Thunderbird, LibreOffice) appelle hors navigateur : pas de CORS non plus. Seuls les sites web
  déclarent leur origine.
- **Pagination** : `limit` vaut 200 au plus et il n'y a pas de pagination en V1 ; `total` dit
  combien d'agents la personne peut voir, un consommateur affiche « 200+ » au-delà.

## `GET /api/v1/agents`

| Paramètre | Obligatoire | Description |
|---|---|---|
| `input` | non | Ne garder que les agents qui acceptent cette entrée (voir le vocabulaire). Une valeur inconnue donne `400 invalid_query`. |
| `limit` | non | 1 à 200, par défaut 100. |

Réponse `200` :

```json
{
  "source": "mesagents",
  "total": 2,
  "agents": [{
    "id": "7f3c…",
    "name": "Rédacteur de notes administratives",
    "description": "Aide à rédiger des notes de service…",
    "origin": "shared",
    "categories": ["redaction"],
    "tags": ["notes"],
    "version": 3,
    "visibility": "ministry",
    "status": "published",
    "inputs": ["text", "selection", "document"],
    "outputs": ["text", "replacement"],
    "greeting": "Bonjour, je peux vous aider à rédiger…",
    "examples": ["Rédige une note de service…"],
    "model": "7f3c…",
    "updated_at": "2026-10-06T10:12:00+00:00",
    "url": "https://…/catalog/7f3c…"
  }]
}
```

- **`origin`** vaut `mine` (créé par la personne) ou `shared` (partagé avec elle). Mon portail
  les présente comme « Le vôtre » et « Partagé par des collègues ».
- **`model`** est la valeur à passer dans `model` de `POST /v1/chat/completions`. Aujourd'hui
  égale à `id` ; un consommateur ne doit pas le supposer.
- **`inputs`** dit sur quoi l'agent sait travailler ; **`outputs`** ce qu'il rend. Un
  consommateur filtre sur son contexte : un plug-in bureautique ne propose que les agents qui
  acceptent `selection` ou `document`.
- **`status`** vaut `draft`, `published` ou `submitted`. Les brouillons ne figurent que dans
  `origin: mine`. Un agent archivé n'apparaît jamais.
- **`url`** est une URL `https` absolue vers la page de l'agent dans Mes agents.
- Tailles : `name` ≤ 200, `description` ≤ 2 000, `greeting` ≤ 2 000, `examples` ≤ 20 × 500.
- Tri : les agents de la personne d'abord, puis les partagés, par date de mise à jour
  décroissante.

### Vocabulaire fermé

`inputs` : `text`, `selection`, `document`, `email`, `thread`, `meeting`, `collection`, `page`.
`outputs` : `text`, `replacement`, `insertion`.

Ajouter une valeur est un geste de contrat : ce fichier d'abord, puis Mes agents, puis les
consommateurs. Une valeur inconnue dans une fiche est ignorée par le consommateur, jamais
affichée.

## `GET /v1/models`

Même liste, au format OpenAI, pour les clients qui ne savent lire que cela (plug-ins). Chaque
entrée porte `id`, `name`, `created`, `owned_by: "myagents"` et `info.meta.description`.

Avec la clé partagée du socle à la place d'un jeton utilisateur, la liste est celle des agents
partagés (sans distinction de personne) : c'est le socle qui applique ses propres droits.

## `POST /v1/chat/completions`

Corps au format OpenAI : `model` (identifiant d'agent), `messages` (rôles `user` et `assistant`
seulement, 500 messages au plus, **120 000 caractères par message** au plus), `stream`
(facultatif). Les autres paramètres OpenAI sont ignorés : la configuration de l'agent fait foi.

Contenus longs (transcription d'une réunion, document) : le consommateur les met dans le dernier
message, en un seul morceau, et tronque au-delà de 100 000 caractères en le disant à la personne.
Un contenu qui dépasse la fenêtre du modèle est refusé par celui-ci : la route répond alors
`502 llm_unavailable`. Au-delà de 120 000 caractères, `422` avant tout appel.

Convention de contexte : le consommateur met le contenu sur lequel l'agent doit travailler dans
le dernier message `user`, avec une consigne courte avant. Exemple pour une sélection :

```
Reformule le passage suivant.

<<<
…texte sélectionné…
>>>
```

Réponse `200` au format OpenAI (`choices[0].message.content`). Avec `stream: true`, un flux SSE
qui porte la réponse **entière en un seul morceau** puis `data: [DONE]` : la garde de sortie
contrôle la réponse complète avant toute émission. Un consommateur n'a rien à faire de plus
qu'avec un flux ordinaire.

Un agent qui n'est pas accessible à la personne répond `404 model_not_found`, sans distinguer
« n'existe pas » de « pas pour vous ».

## Erreurs

Sur `/api/v1/agents`, le corps est `{"error": {"code": "…", "message": "…"}}` :

| Statut | `code` | Cas |
|---|---|---|
| 400 | `invalid_query` | `input` inconnu, `limit` hors bornes |
| 401 | `invalid_token` | Jeton absent, expiré, mal signé, ou sans `sub` |
| 403 | `audience_mismatch` | `aud` sans `mesagents`, ou `azp` non accepté |
| 403 | `forbidden` | Accès refusé par une garde du service (groupe exigé pendant la bêta) |
| 429 | `rate_limited` | Accompagné de `Retry-After` |

Sur `/v1/*`, le format est celui d'OpenAI : `{"error": {"message", "type", "code"}}`, avec les
mêmes codes, plus `model_not_found` (404), `blocked_input` et `blocked_output` (422, `message`
est à afficher tel quel à la personne) et `llm_unavailable` (502).

## Les droits, tels que Mes agents les applique

| Visibilité | Qui voit et lance |
|---|---|
| `private` | la personne qui l'a créé |
| `community` | elle, et les membres du groupe déclaré (`community_path`) |
| `ministry` | tout compte admis sur la bêta |

Un agent `draft` n'est visible que de son auteur. `published` et `submitted` sont partagés selon
la visibilité. `archived` n'est jamais servi. La même règle vaut pour le catalogue de Mes agents,
pour `GET /api/v1/agents`, pour `GET /v1/models` et pour `POST /v1/chat/completions`.

## Comportement attendu du consommateur

- Lister à l'ouverture de l'écran, pas à chaque frappe ; garder la liste au plus quelques
  minutes.
- Filtrer sur `inputs` selon le contexte, afficher `origin`, `name` et `description` en texte.
- Lancer par `POST /v1/chat/completions` avec un délai d'au moins 120 s ; une réponse `422`
  s'affiche telle quelle (`error.message`), une `502` dit « l'agent ne répond pas ».
- Un service injoignable ou un `403` masque la section « Agents » sans bloquer l'écran.

## Keycloak

Portée optionnelle `mesagents-agents` : mapper d'audience `mesagents` (jeton d'accès) et mapper
de groupes en chemins complets. À affecter en optionnel aux clients `mysearch`,
`mycollections-front`, `mes-reunions`, `bootstrap-iassistant`, `mirai-extension` ; dans le realm
des previews, au client `mirai-preview`. Le consommateur la demande dans `scope`
(`openid profile email mesagents-agents`). Le JSON prêt à importer est dans
`keycloak/mesagents-agents.client-scope.json`.
