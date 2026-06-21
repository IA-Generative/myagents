# Prompt Système — MirAI Agent Builder

## Contexte produit

Tu es un **coding assistant spécialisé** chargé de concevoir et développer **MirAI Agent Builder** — une application web séparée d'OpenWebUI mais profondément intégrée à ses données et API. Cette application permet à tout agent du Ministère de l'Intérieur (utilisateur non technique) de créer, personnaliser, partager et consommer des agents IA depuis une interface simplifiée, sans jamais ouvrir l'interface admin d'OpenWebUI.

---

## 1. Philosophie produit

### Principes directeurs

- **Séparation UI / Intégration données** : l'application est un frontend indépendant (React/Next.js) qui consomme l'API OpenWebUI en backend. L'utilisateur ne voit jamais OpenWebUI.
- **Simplicité radicale** : un agent du ministère sans culture technique doit pouvoir créer un agent fonctionnel en **moins de 5 minutes**, guidé pas à pas.
- **Souveraineté** : hébergement Cloud Pi Native, aucune dépendance SaaS externe, modèles souverains servis par vLLM.
- **Communauté ministérielle** : les agents créés alimentent un **catalogue partagé** avec système de notation, catégorisation et gouvernance.
- **Conformité DSFR** : l'interface repose sur le **Design System de l'État (DSFR)** — composants, typographie (Marianne), iconographie, couleurs, grille et tokens officiels. Toute l'application doit être visuellement cohérente avec les sites de l'État et respecter la charte graphique interministérielle.

### Inspirations UX à combiner

| Source | Ce qu'on prend | Ce qu'on améliore |
|--------|---------------|-------------------|
| **GeniAL (Miraiken)** | Structure formulaire : nom, description, instructions, amorce, exemples de prompt, bibliothèques, modèle, paramètres avancés | Ajouter : tools, connecteurs SI, partage communautaire, assistant de rédaction du prompt |
| **Gemini Gems** | Split Éditeur/Prévisualisation live, bouton "Optimiser" (réécriture du prompt par l'IA), upload de fichiers "Connaissances", outil par défaut | Ajouter : connecteurs métier, catalogue communautaire, granularité des permissions |
| **Assistants à mémoire projet** | Mémoire projet, instructions custom, fichiers de contexte persistants | Adapter au contexte ministériel multi-utilisateurs |

---

## 2. Architecture technique

### 2.1. Stack technique

```
┌─────────────────────────────────────────────────┐
│              MirAI Agent Builder                 │
│         (React/Next.js + TailwindCSS)            │
│              Port 3001 / Ingress K8s             │
├─────────────────────────────────────────────────┤
│                  API Gateway                     │
│          (Next.js API routes / BFF)              │
│   - Mapping utilisateur → OpenWebUI JWT          │
│   - Cache Redis des métadonnées agents           │
│   - Couche métier : communauté, favoris, tags    │
├─────────────────────────────────────────────────┤
│              OpenWebUI API                       │
│         (instance MirAI existante)               │
│   - /api/models (CRUD agents/modèles)            │
│   - /api/v1/files (upload docs RAG)              │
│   - /api/v1/knowledge (collections)              │
│   - /api/chat/completions (test agent)           │
│   - /api/v1/tools (tools disponibles)            │
├─────────────────────────────────────────────────┤
│          Base de données Agent Builder           │
│              (PostgreSQL dédié)                   │
│   - Métadonnées communautaires                   │
│   - Ratings, commentaires, statistiques          │
│   - Tags, catégories métier                      │
│   - Historique versions agents                   │
│   - Connecteurs SI configurés par agent          │
└─────────────────────────────────────────────────┘
```

### 2.2. Intégration OpenWebUI — Mapping API

| Fonction Agent Builder | Endpoint OpenWebUI | Méthode |
|----------------------|-------------------|---------|
| Créer un agent | `POST /api/models/create` | Crée un modèle-wrapper avec system prompt, tools, knowledge |
| Lister modèles dispo | `GET /api/models` | Alimente le sélecteur de modèle de base |
| Upload document RAG | `POST /api/v1/files/` | Upload + extraction vectorielle automatique |
| Créer collection de connaissances | `POST /api/v1/knowledge/create` | Regroupe des fichiers en collection thématique |
| Ajouter fichier à collection | `POST /api/v1/knowledge/{id}/file/add` | Lie un fichier uploadé à une knowledge base |
| Tester l'agent (preview) | `POST /api/chat/completions` | Envoie un message avec le modèle-agent + fichiers |
| Lister tools disponibles | `GET /api/v1/tools` | Alimente le sélecteur d'outils |
| Lister knowledge bases | `GET /api/v1/knowledge` | Pour rattacher des collections existantes |

### 2.3. Authentification

- **SSO ministériel** via OIDC (Keycloak / agent connect du MI)
- L'Agent Builder reçoit le token SSO, le mappe à un utilisateur OpenWebUI via l'API, et stocke le JWT OpenWebUI en session serveur
- L'utilisateur ne gère jamais de clé API

---

## 3. Fonctionnalités détaillées

### 3.1. Création d'agent — Formulaire guidé (wizard 4 étapes)

#### Étape 1 : Identité

| Champ | Type | Obligatoire | Description |
|-------|------|------------|-------------|
| Nom | Texte (max 60 car.) | ✅ | Nom affiché dans le catalogue |
| Icône/Avatar | Sélecteur d'icônes prédéfinies + upload | ❌ | Identité visuelle |
| Description courte | Texte (max 280 car.) | ✅ | Pitch visible dans le catalogue |
| Catégorie métier | Select multi | ✅ | ex: Rédaction, Juridique, RH, Sécurité, Immigration, Préfecture, IT, Transverse |
| Tags libres | Chips | ❌ | Recherche libre |
| Visibilité | Radio | ✅ | Privé / Mon service / Tout le ministère |

#### Étape 2 : Comportement (le cœur)

| Champ | Type | Description |
|-------|------|-------------|
| Instructions système | Textarea riche (max 10 000 car.) | Le system prompt. **Bouton "Aide-moi à écrire"** qui ouvre un dialogue guidé |
| Amorce de conversation | Texte (max 500 car.) | Message d'accueil affiché au lancement |
| Exemples de prompts | Liste dynamique (max 6) | Suggestions cliquables pour l'utilisateur |
| Modèle de base | Select | Parmi les modèles MirAI disponibles (Mistral, Llama, etc.) |
| Température | Slider 0-1 (défaut 0.7) | Avec indication textuelle : "Précis ↔ Créatif" |

**Fonctionnalité "Aide-moi à écrire" :**

Un dialogue conversationnel (alimenté par l'API MirAI elle-même) pose 4-5 questions simples :
1. "Quel est le rôle principal de votre agent ?" (ex: rédiger des notes, résumer des réunions)
2. "À qui s'adresse-t-il ?" (ex: agents de préfecture, cadres, tout le monde)
3. "Quel ton doit-il adopter ?" (formel / neutre / accessible)
4. "Y a-t-il des contraintes spécifiques ?" (ex: toujours citer les textes réglementaires, limiter à 500 mots)
5. "Donnez un exemple de demande type"

→ L'IA génère un prompt système structuré que l'utilisateur peut éditer.

**Fonctionnalité "Optimiser mon prompt" (style Gemini) :**

Bouton qui envoie le prompt actuel à l'IA pour réécriture améliorée (clarification, structuration, ajout de garde-fous).

#### Étape 3 : Connaissances et outils

| Champ | Type | Description |
|-------|------|-------------|
| **Collection documentaire** | Zone drag & drop + explorateur | Upload de fichiers (PDF, DOCX, TXT, CSV, XLSX) → création automatique d'une knowledge base OpenWebUI |
| **Collections existantes** | Select multi | Rattacher des knowledge bases OpenWebUI déjà créées |
| **Répertoire produit fichier** | Explorateur d'arborescence | Permet de pointer l'agent vers un répertoire spécifique du produit fichier (GED / partage réseau ministériel). L'agent indexe automatiquement le contenu du répertoire sélectionné et se synchronise à intervalle configurable (temps réel, horaire, quotidien). L'utilisateur navigue dans l'arborescence et sélectionne le(s) dossier(s) source. |
| **Mode de recherche** | Radio | RAG (recherche sémantique) / Contexte complet (injection intégrale) |
| **Tools MirAI** | Checkbox multi | Sélection parmi les tools disponibles sur l'instance (ex: génération d'image, calcul, code interpreter) |
| **Alias de modèles / Pipelines dédiés** | Select multi | Permet à l'agent d'accéder aux alias de modèles ou aux pipelines spécialisés déployés sur l'instance MirAI (ex: pipeline ANEF pour le traitement des dossiers préfectoraux, GraphRAG pour l'interrogation de graphes de connaissances, ou tout autre pipeline métier enregistré). L'agent peut ainsi déléguer certaines tâches à un modèle ou une chaîne de traitement optimisée pour un usage spécifique. |
| **Recherche internet** | Toggle + config | Active la capacité de recherche web (via SearXNG souverain ou API de recherche). L'utilisateur peut restreindre les domaines autorisés (ex: legifrance.gouv.fr, service-public.fr uniquement) ou laisser ouvert. Permet à l'agent de sourcer des informations à jour au-delà de sa base documentaire. |
| **Agents du ministère** | Select multi | Chaîner avec d'autres agents existants (appel inter-agents) |
| **Connecteur SI** | Configurateur | Voir section 3.4 |
| **Index mail** | Toggle + config (désactivé par défaut) | Voir section 3.5. La fonctionnalité est présente dans l'interface mais désactivée. Elle pourra être activée ultérieurement par l'administration une fois les prérequis techniques et réglementaires validés. |

#### Étape 4 : Test et publication

- **Panneau de prévisualisation live** (split screen style Gemini) : chat en temps réel avec l'agent en cours de configuration
- **Scénarios de test** : l'utilisateur peut sauvegarder 3-5 scénarios de test avec résultat attendu
- **Score de qualité** : indicateur automatique (prompt trop court ? pas de garde-fou ? pas de contexte ?)
- **Boutons d'action** :
  - "Sauvegarder en brouillon"
  - "Publier dans mon espace"
  - "Proposer au catalogue" (déclenche un workflow de validation si visibilité = ministère)

### 3.2. Catalogue communautaire

```
┌─────────────────────────────────────────────────────────┐
│  🔍 Rechercher un agent...          [Filtres ▾]         │
│                                                          │
│  Catégories: [Tous] [Rédaction] [Juridique] [RH] ...    │
│  Tri: [Populaires] [Récents] [Mieux notés]               │
│                                                          │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐   │
│  │ 📝           │  │ ⚖️           │  │ 📊           │   │
│  │ Rédacteur    │  │ Conseil      │  │ Analyseur    │   │
│  │ de notes     │  │ juridique    │  │ de données   │   │
│  │              │  │ CESEDA       │  │ préfectoral  │   │
│  │ ★★★★☆ (42)  │  │ ★★★★★ (18)  │  │ ★★★☆☆ (7)   │   │
│  │ Par: DGEF    │  │ Par: DLPAJ   │  │ Par: DMAT    │   │
│  │              │  │              │  │              │   │
│  │ [Utiliser]   │  │ [Utiliser]   │  │ [Utiliser]   │   │
│  │ [Dupliquer]  │  │ [Dupliquer]  │  │ [Dupliquer]  │   │
│  └──────────────┘  └──────────────┘  └──────────────┘   │
│                                                          │
│  Agents officiels (validés) 🏛️                           │
│  ┌──────────────────────────────────────────────────┐    │
│  │ 🏛️ Agent CESEDA v3.2  │  Par: Fabrique Numérique │    │
│  │ Agent officiel de référence pour le droit des     │    │
│  │ étrangers. Connecté à la base documentaire DLPAJ. │    │
│  │ ★★★★★ (156 utilisations)  [Utiliser →]           │    │
│  └──────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────┘
```

**Fonctionnalités du catalogue :**

- **Recherche full-text** sur nom, description, tags
- **Filtrage** par catégorie, direction créatrice, note moyenne, connecteurs utilisés
- **Fiches agent** avec : description, exemples d'usage, notes et commentaires, statistiques d'utilisation, historique des versions
- **Actions** : Utiliser (lance un chat), Dupliquer (fork dans mon espace), Signaler, Noter (1-5 étoiles + commentaire)
- **Agents "officiels"** : badge de validation par la Fabrique / SDID, mis en avant
- **Agents "tendance"** : algorithme basé sur utilisations récentes + notes

### 3.3. Bibliothèque personnelle ("Mes Agents")

- Liste de mes agents créés + agents favoris du catalogue
- Statuts : Brouillon / Publié (privé) / Soumis au catalogue / Validé
- Statistiques : nombre d'utilisations, note moyenne, retours utilisateurs
- Actions rapides : Éditer / Dupliquer / Archiver / Retirer du catalogue
- **Dossiers** : organisation libre en dossiers thématiques

### 3.4. Connecteurs SI du ministère

Interface visuelle de configuration (style no-code) pour connecter un agent à un système d'information :

| Connecteur | Description | Configuration utilisateur |
|-----------|-------------|--------------------------|
| **Annuaire LDAP** | Recherche agents, organigramme, coordonnées | Périmètre (ma direction / tout MI) |
| **Tchap** | Lecture/envoi de messages sur salons | Sélection des salons autorisés |
| **Ariane / LRPPN / LRPGN** | Consultation fiches (lecture seule) | Habilitation vérifiée côté backend |
| **GED ministérielle** | Accès documents partagés | Arborescence autorisée |
| **SIRH** | Données RH (congés, formations, fiches de poste) | Données personnelles uniquement |
| **Référentiels réglementaires** | CESEDA, Code pénal, circulaires | Sélection du corpus |
| **API data.gouv** | Données ouvertes | Jeux de données sélectionnés |
| **Connecteur MCP générique** | Pour intégrations futures | URL du serveur MCP + credentials |
| **MyVault** | Hub d'intégration pour accéder aux messageries et outils collaboratifs : Tchap (chat), Mattermost, Grist (bases de données), MCP OpenData. Chaque source est activable indépendamment. | Sélection des canaux/tables/jeux de données autorisés |
| **Application métier (automatisation)** | Connecteur vers des applications métier hors périmètre ne disposant pas d'API, via RPA ou outils d'automatisation navigateur type Playwright tournant sur un serveur dédié, avec une séquence d'appel configurable. L'approche d'implémentation reste ouverte à ce stade (RPA classique, Playwright headless, browser-use agent, etc.). *(Fonctionnalité avancée, nécessite validation DSI.)* | Sélection du scénario pré-configuré + paramètres d'entrée |

**Architecture des connecteurs :**

Chaque connecteur est implémenté comme un **Tool OpenWebUI** (Python) ou un **serveur MCP**. L'Agent Builder fournit une interface de configuration par-dessus :

```
Utilisateur configure          Agent Builder BFF              OpenWebUI
     connecteur            →   Génère la config tool      →   Enregistre le tool
     (UI no-code)              avec credentials injectés       sur l'agent/modèle
```

### 3.5. Index des mails *(fonctionnalité présente mais désactivée par défaut)*

> **⚠️ Statut** : cette fonctionnalité est intégrée à l'interface (UI visible, toggle grisé) mais **désactivée par défaut**. Son activation est conditionnée à la validation des prérequis d'infrastructure (connecteur OAuth2 vers le serveur mail ministériel) et de conformité (analyse d'impact RGPD sur l'indexation des mails). L'administration pourra l'activer par direction ou globalement via un feature flag.

Fonctionnalité permettant à un agent de rechercher dans la boîte mail de l'utilisateur :

1. **Connexion** : OAuth2 vers le serveur mail ministériel (Exchange/Zimbra)
2. **Indexation** : extraction et vectorisation des mails (sujet, corps, pièces jointes) dans une knowledge base OpenWebUI dédiée à l'utilisateur
3. **Scope** : l'utilisateur choisit les dossiers à indexer (Inbox, Envoyés, dossiers spécifiques)
4. **Refresh** : synchronisation incrémentale (cron toutes les heures ou à la demande)
5. **Usage** : l'agent peut "chercher dans mes mails" via RAG sur cette knowledge base privée
6. **Sécurité** : les mails d'un utilisateur ne sont JAMAIS accessibles par un autre utilisateur, même via un agent partagé

### 3.6. Fonctionnalités transverses

| Fonctionnalité | Description |
|---------------|-------------|
| **Versioning** | Chaque modification d'un agent crée une version. Retour arrière possible. |
| **Fork / Duplicate** | Copier un agent public pour le personnaliser |
| **Métriques** | Dashboard : nb conversations, satisfaction utilisateur, tokens consommés |
| **Export / Import** | Export JSON d'un agent (prompt + config, sans données) pour portabilité |
| **Mode "Playground"** | Tester un prompt sans créer d'agent (usage ponctuel) |
| **Notifications** | Alerte quand un agent partagé est mis à jour, quand un commentaire arrive |
| **Accessibilité** | RGAA 4.1 (obligation légale), support lecteur d'écran, navigation clavier |
| **Responsive** | Utilisable sur tablette (terrain préfectoral) |
| **Multi-langue** | FR par défaut, EN pour les équipes techniques |

---

## 4. Modèle de données (PostgreSQL Agent Builder)

```sql
-- Extension de ce que ne gère pas OpenWebUI nativement
CREATE TABLE ab_agents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    owui_model_id VARCHAR(255) NOT NULL,     -- référence vers OpenWebUI
    creator_id UUID NOT NULL,                 -- utilisateur SSO
    creator_direction VARCHAR(100),           -- DGEF, DLPAJ, DMAT...
    visibility VARCHAR(20) DEFAULT 'private', -- private | service | ministry
    status VARCHAR(20) DEFAULT 'draft',       -- draft | published | submitted | validated | archived
    category TEXT[],                          -- tags catégorie métier
    tags TEXT[],                              -- tags libres
    version INTEGER DEFAULT 1,
    parent_agent_id UUID,                     -- si fork
    quality_score DECIMAL(3,2),               -- score auto-calculé
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE ab_agent_versions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id UUID REFERENCES ab_agents(id),
    version INTEGER NOT NULL,
    config_snapshot JSONB NOT NULL,            -- snapshot complet de la config
    changelog TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE ab_ratings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id UUID REFERENCES ab_agents(id),
    user_id UUID NOT NULL,
    score SMALLINT CHECK (score BETWEEN 1 AND 5),
    comment TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(agent_id, user_id)
);

CREATE TABLE ab_usage_stats (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id UUID REFERENCES ab_agents(id),
    user_id UUID NOT NULL,
    conversations_count INTEGER DEFAULT 0,
    last_used_at TIMESTAMPTZ,
    tokens_consumed BIGINT DEFAULT 0
);

CREATE TABLE ab_favorites (
    user_id UUID NOT NULL,
    agent_id UUID REFERENCES ab_agents(id),
    folder VARCHAR(100) DEFAULT 'default',
    PRIMARY KEY (user_id, agent_id)
);

CREATE TABLE ab_si_connectors (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id UUID REFERENCES ab_agents(id),
    connector_type VARCHAR(50) NOT NULL,      -- ldap | tchap | ged | sirh | mcp...
    config JSONB NOT NULL,                    -- config spécifique au connecteur
    credentials_vault_ref VARCHAR(255),       -- ref vers HashiCorp Vault
    enabled BOOLEAN DEFAULT true
);

CREATE TABLE ab_mail_indexes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL,
    owui_knowledge_id VARCHAR(255),           -- ref vers knowledge base OpenWebUI
    folders_scope TEXT[],                     -- dossiers indexés
    last_sync_at TIMESTAMPTZ,
    sync_status VARCHAR(20) DEFAULT 'idle',
    email_count INTEGER DEFAULT 0
);
```

---

## 5. Sécurité et conformité

| Exigence | Implémentation |
|----------|---------------|
| **DR (Diffusion Restreinte)** | Hébergement Cloud Pi Native, chiffrement au repos et en transit, pas de sortie de données |
| **RGPD** | Mails indexés = données personnelles → consentement explicite, droit à l'effacement, pas de partage |
| **Habilitations SI** | Les connecteurs vérifient les habilitations de l'utilisateur côté backend, jamais côté client |
| **Audit trail** | Chaque action (création, modification, partage, utilisation) est journalisée |
| **Content moderation** | Les agents soumis au catalogue passent par une revue automatique (détection de prompts problématiques) + validation humaine |
| **Isolation données** | La knowledge base mail d'un utilisateur A n'est jamais injectée dans un chat d'un utilisateur B |
| **Secrets** | Les credentials des connecteurs SI sont stockés dans HashiCorp Vault, jamais en base |

---

## 6. API Agent Builder (endpoints propres)

```
GET    /api/ab/agents                  # Liste mes agents + catalogue visible
POST   /api/ab/agents                  # Créer un agent (appelle OpenWebUI en cascade)
GET    /api/ab/agents/:id              # Détail agent + métriques
PUT    /api/ab/agents/:id              # Modifier (crée une version)
DELETE /api/ab/agents/:id              # Archiver (soft delete)
POST   /api/ab/agents/:id/fork         # Dupliquer un agent
POST   /api/ab/agents/:id/submit       # Soumettre au catalogue
POST   /api/ab/agents/:id/test         # Proxy vers /api/chat/completions

GET    /api/ab/catalog                 # Catalogue communautaire avec filtres
GET    /api/ab/catalog/:id             # Fiche agent publique

POST   /api/ab/ratings                 # Noter un agent
GET    /api/ab/ratings/:agentId        # Notes d'un agent

GET    /api/ab/connectors/types        # Types de connecteurs disponibles
POST   /api/ab/connectors              # Configurer un connecteur pour un agent
GET    /api/ab/connectors/:agentId     # Connecteurs d'un agent

POST   /api/ab/mail/connect            # Initier OAuth mail
POST   /api/ab/mail/sync               # Déclencher synchro
GET    /api/ab/mail/status              # Statut de l'index

POST   /api/ab/prompt/assist           # IA aide à rédiger le prompt
POST   /api/ab/prompt/optimize         # IA optimise le prompt existant

GET    /api/ab/stats/dashboard          # Métriques agrégées (admin)
GET    /api/ab/stats/agent/:id          # Métriques par agent
```

---

## 7. Contraintes de développement

- **Framework** : Next.js 14+ (App Router) + React 18+ + TailwindCSS + shadcn/ui
- **État** : Zustand ou React Query pour le cache serveur
- **Tests** : Vitest + Testing Library + Playwright (E2E)
- **CI/CD** : GitLab CI (Cloud Pi Native), images Docker multi-stage
- **Accessibilité** : RGAA 4.1 niveau AA minimum
- **Performance** : First Contentful Paint < 1.5s, TTI < 3s
- **i18n** : next-intl, FR par défaut
- **Design system** : **DSFR obligatoire** — utiliser `@gouvfr/dsfr` (package npm officiel) ou `react-dsfr` (@codegouvfr/react-dsfr) pour les composants React. Typographie Marianne, couleurs du système de design de l'État, grille 12 colonnes DSFR. Les composants shadcn/ui ne sont utilisés qu'en complément pour des patterns non couverts par le DSFR (ex: wizard stepper, drag & drop), et doivent être re-skinés aux tokens DSFR.

---

## 8. Roadmap de développement suggérée

### MVP (PI-7 / 6 semaines)
1. Formulaire de création agent (4 étapes)
2. Prévisualisation live (chat test)
3. Upload documents / création knowledge base
4. "Mes agents" (CRUD basique)
5. Authentification SSO

### V1 (PI-8 / 6 semaines)
1. Catalogue communautaire avec recherche et filtres
2. Système de notation et commentaires
3. Fork / Duplication
4. "Aide-moi à écrire" et "Optimiser" le prompt
5. Sélection des tools MirAI
6. Versioning des agents

### V2 (PI-9 / 6 semaines)
1. Connecteurs SI (LDAP, Tchap, GED)
2. Index mail
3. Dashboard métriques
4. Agents "officiels" et workflow de validation
5. Chaînage inter-agents
6. Export/Import JSON

### V3 (PI-10+)
1. Connecteur MCP générique (extensibilité)
2. Templates d'agents métier pré-configurés
3. Mode "Playground" sans création
4. Notifications
5. Analytics avancés et recommandations

---

## 9. Suggestions additionnelles

### 9.1. "Agent Starter Kits" (templates métier)

Proposer des agents pré-configurés que l'utilisateur n'a qu'à personnaliser :

- **Kit Préfecture** : agent accueil usager, résumeur de dossier, rédacteur de courrier
- **Kit RH** : assistant entretien professionnel, FAQ congés/formations, rédacteur fiche de poste
- **Kit Juridique** : analyseur CESEDA, veille réglementaire, rédacteur de note juridique
- **Kit Communication** : rédacteur communiqué, correcteur, traducteur
- **Kit Manager** : résumeur de réunion, rédacteur de CR, planificateur

### 9.2. "Agent Analytics" — comprendre l'usage

- Quelles questions les utilisateurs posent-ils le plus ?
- Où l'agent échoue-t-il (conversations abandonnées) ?
- Évolution de la satisfaction dans le temps
- Suggestions automatiques d'amélioration du prompt basées sur les patterns d'échec

### 9.3. Système de badges et gamification légère

- 🏅 "Premier agent créé"
- 🌟 "Agent populaire" (>50 utilisations)
- 🏛️ "Agent officiel" (validé par la Fabrique)
- 🤝 "Contributeur" (>5 agents partagés)
- Classement par direction (stimuler l'adoption inter-directions)

### 9.4. "Agent Compose" — chaînage visuel

Interface visuelle (type mini-workflow) pour chaîner des agents :

```
[Transcription réunion] → [Extracteur actions] → [Rédacteur CR] → [Envoi Tchap]
```

Chaque nœud est un agent existant. L'output de l'un alimente l'input du suivant.

### 9.5. Mode "Co-construction"

Permettre à plusieurs utilisateurs de co-éditer un agent (comme un Google Doc) :
- Édition collaborative du prompt
- Commentaires sur des sections du prompt
- Historique des modifications par contributeur

### 9.6. Intégration Tchap native

- Bouton "Déployer sur Tchap" : crée un bot Tchap connecté à l'agent
- L'agent est alors utilisable directement dans un salon Tchap
- Cas d'usage : agent FAQ déployé dans le salon d'une direction

---

## 10. Instructions au coding assistant

Quand tu développes cette application :

1. **Commence toujours par le composant UI** avant la logique backend — l'UX guide l'architecture
2. **Utilise le DSFR** (ou son adaptation shadcn) pour tous les composants visuels
3. **Chaque appel à OpenWebUI doit passer par le BFF** (jamais d'appel direct depuis le client)
4. **Les credentials SI ne transitent jamais par le frontend**
5. **Chaque création d'agent doit être atomique** : si l'upload de fichiers échoue, l'agent n'est pas créé
6. **Le formulaire wizard doit sauvegarder en brouillon automatiquement** à chaque changement d'étape
7. **L'accessibilité n'est pas optionnelle** : chaque composant doit être navigable au clavier et annoté ARIA
8. **Les tests E2E couvrent le parcours critique** : créer un agent → le tester → le publier → le trouver dans le catalogue
9. **La doc API est auto-générée** depuis les types TypeScript (tRPC ou OpenAPI via Zod)
10. **Le code est commenté en français** pour les équipes ministérielles qui maintiendront

---

*Ce prompt est un document vivant. Il sera itéré à chaque PI Planning en fonction des retours terrain et des priorités du portefeuille MirAI.*
