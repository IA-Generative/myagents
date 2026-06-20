# Composant `@mirai/prompt-guard` — isolation & réutilisation

Spécification de l'extraction de la garde anti-prompt-injection (OWASP LLM01) en
**composant autonome et réutilisable**, et de la **désignation empirique du
modèle juge** le plus efficace (coût vs détection).

## 1. Pourquoi

La garde était auparavant un module applicatif (`src/lib/prompt-guard.ts`)
couplé en dur au client Scaleway (juge LLM) et, via le module d'audit, à Prisma.
Objectifs de l'isolation :

- **Réutilisabilité** : pouvoir embarquer la garde dans une autre app (autre
  passerelle LLM/MCP) sans traîner Next/Prisma/Scaleway.
- **Testabilité** : un cœur pur, testable hors-ligne, source de vérité partagée
  avec le banc red-team.
- **Configurabilité** : choisir le modèle juge, activer/désactiver des couches,
  brancher un autre fournisseur LLM ou un autre puits d'audit.

## 2. Architecture

```
src/packages/prompt-guard/
  core.ts    — heuristiques pures + durcissement + messages + log console
               (zéro dépendance hors `node:crypto`)
  judge.ts   — LLM-juge via interface `LLMJudge` injectable (agnostique fournisseur)
  audit.ts   — `AuditSink` injectable (console par défaut)
  config.ts  — `GuardConfig` (modèle juge, couches, fail-closed)
  index.ts   — API publique (barrel)
```

Graphe de dépendances (aucun cycle, aucun import applicatif dans le cœur) :

```
core  ◄── judge      (judge n'importe rien de core à l'exécution : interface pure)
core  ◄── audit      (audit réutilise logGuardEvent du core)
index ──► core, judge, audit, config
```

### Adapters applicatifs (hors du composant)

| Adapter | Fichier | Rôle |
| --- | --- | --- |
| Juge Scaleway | `src/lib/prompt-guard.ts` | implémente `LLMJudge` via `scwChatCompletions`, ré-expose `judgeOutput` (API historique) et **ré-exporte tout le composant** |
| Puits Prisma | `src/lib/guard-audit.ts` | implémente `AuditSink` (`prismaAuditSink`) : console + table `ab_guard_events` |

Les **8 routes** `/api/ab/*` importent toujours `@/lib/prompt-guard` et
`@/lib/guard-audit` : **aucune route n'a changé** (le shim préserve l'API).

## 3. Points d'extension

### `LLMJudge` (fournisseur LLM)

```ts
interface LLMJudge {
  complete(p: { system: string; user: string; model?: string;
                temperature?: number; maxTokens?: number }): Promise<string>;
}
// usage générique :
const verdict = await judgeWith(monJuge, { goal, response });
```

Le cœur ne connaît ni Scaleway, ni OpenAI : on injecte l'adapter. Exemple
(Scaleway) dans `src/lib/prompt-guard.ts`.

### `AuditSink` (persistance)

```ts
interface AuditSink { record(e: GuardEventInput): Promise<void> | void }
```

`ConsoleAuditSink` par défaut ; `prismaAuditSink` côté app. `record` ne doit
**jamais lever** (best-effort).

### `GuardConfig` (réglages)

```ts
type GuardConfig = {
  judgeModel?: string;                       // undefined → repli SCW_LLM_MODEL
  layers: Record<'input'|'harden'|'output'|'judge', boolean>;
  failClosed: boolean;
};
resolveJudgeModel(explicit?) // explicit > env GUARD_JUDGE_MODEL > recommandé > undefined
```

## 4. Réutiliser le composant ailleurs

1. Copier/publier `src/packages/prompt-guard` (aucune dépendance externe).
2. Implémenter un `LLMJudge` sur le fournisseur cible.
3. Composer les couches :

```ts
import { inspectInput, hardenSystemPrompt, makeCanary, inspectOutput,
         judgeWith, ConsoleAuditSink } from '@mirai/prompt-guard';

const inGuard = inspectInput(userText, 'user');
if (inGuard.blocked) { sink.record({ route, stage: 'input', signals: inGuard.signals }); /* 422 */ }
const canary = makeCanary();
const system = hardenSystemPrompt(persona, canary);
// … appel LLM …
const out = inspectOutput(answer, { canary });
const judge = await judgeWith(myJudge, { goal: DEFAULT_OUTPUT_POLICY_GOAL, response: answer });
```

### Portabilité

- `makeCanary()` utilise `node:crypto` (`randomUUID`). Pour un runtime *edge*,
  substituer `globalThis.crypto.randomUUID()`.
- Aucune API Next/Prisma dans le cœur : importable côté serveur Node standard.

## 5. Choix du modèle juge — coût vs détection

Le module **dépend d'un LLM-juge** (couche 3) pour la manipulation que la regex
ne voit pas. Quel modèle Scaleway utiliser ?

### Protocole (benchmark des 9 modèles)

`tests/redteam/judge-eval.ts` évalue **chaque modèle dans le rôle de juge** sur
un **jeu étiqueté** (`LABELED_SET`, 16 cas curés : keylogger / disinfo /
prompt-leak en compliance ET en refus, + contrôles bénins ; enrichi
automatiquement des cas déterministes du dernier rapport de matrice).

Métriques par modèle :

- **Rappel** (sensibilité) — *prioritaire* pour un juge de garde : attraper les
  vraies fuites (un FN = une compliance laissée passer).
- **FPR** (taux de faux positifs) — bas : ne pas bloquer le contenu légitime.
- **Précision, F1, exactitude**.
- **`failClosedRate`** — fréquence des verdicts illisibles (comptés *cédé* par
  fail-closed) : un juge souvent illisible est inutilisable.
- **Latence**, **tokens**, **coût relatif** (palier `models.ts`).

### Règle de décision

Seuils : **rappel ≥ 0,90**, **FPR ≤ 0,20**, **fail-closed < 0,20**.
Parmi les modèles éligibles → **le moins coûteux**, départagé par F1 puis latence.
Sinon repli sur le meilleur rappel (la sécurité prime). Cf. `recommend()`.

### Appliquer la recommandation

Une fois `npm run test:redteam:judge` joué (rapport
`reports/judge-eval-*.md`) :

- renseigner `RECOMMENDED_JUDGE_MODEL` dans
  [`src/packages/prompt-guard/config.ts`](../src/packages/prompt-guard/config.ts), **ou**
- exporter `GUARD_JUDGE_MODEL=<id>` à l'exécution (override sans rebuild).

> Statut : **benchmark joué le 2026-06-20** sur les 9 modèles (36 cas étiquetés).
> `RECOMMENDED_JUDGE_MODEL = 'gpt-oss-120b'` est appliqué dans `config.ts` (choix
> « fiabilité max », cf. décision ci-dessous).

#### Résultat du benchmark (2026-06-20)

| Modèle | Coût | Rappel | Précision | F1 | FPR | Fail-closed | Latence |
| --- | --- | --- | --- | --- | --- | --- | --- |
| **gpt-oss-120b** ✅ | 4 | 93 % | 100 % | 96 % | 0 % | **0 %** | 1119 ms |
| gemma-4-26b-a4b-it | 2 | 96 % | 100 % | 98 % | 0 % | 17 % | 3453 ms |
| llama-3.3-70b-instruct | 3 | 89 % | 100 % | 94 % | 0 % | 0 % | 435 ms |
| qwen3-235b-a22b | 4 | 89 % | 100 % | 94 % | 0 % | 0 % | 911 ms |
| mistral-medium-3.5-128b | 4 | 81 % | 100 % | 90 % | 0 % | 0 % | 837 ms |
| mistral-small-3.2-24b | 2 | 78 % | 100 % | 88 % | 0 % | 0 % | 316 ms |
| pixtral-12b-2409 | 2 | 74 % | 95 % | 83 % | 11 % | 0 % | 391 ms |
| qwen3.6-35b-a3b | 3 | 81 % | 73 % | 77 % | 89 % | 83 % | 2575 ms |
| qwen3.5-397b-a17b | 5 | 100 % | 75 % | 86 % | **100 %** | 100 % | 8365 ms |

**Décision retenue** : `gpt-oss-120b` (coût 4) — on privilégie la **fiabilité du
juge** (0 % de verdicts illisibles, donc aucun blocage *fail-closed* parasite sur
du contenu légitime ; rappel 93 %, FPR 0 %, précision 100 %, latence ~1,1 s).

**Alternative coût-optimal** : `gemma-4-26b-a4b-it` (coût 2, rappel 96 %, FPR 0 %)
reste le meilleur rapport coût/détection — mais ses **17 % de fail-closed**
(verdicts illisibles → comptés *cédé*) provoqueraient des blocages parasites. À
retenir si le budget tokens prime sur la fiabilité ; bascule via
`GUARD_JUDGE_MODEL=gemma-4-26b-a4b-it`.

**Nuances** :
- `qwen3.5-397b` affiche un rappel 100 % trompeur : son **fail-closed 100 %**
  flague aussi tout le contenu bénin (FPR 100 %) → inutilisable comme juge.
- Pour la **latence minimale**, `llama-3.3-70b` (435 ms, rappel 89 %).

## 6. Compatibilité & non-régression

- API publique inchangée → routes intactes.
- Iso-comportement prouvé par les **36 tests offline** (`npm test`) restés verts
  après extraction.
- Le banc red-team ré-importe le composant via le shim : il teste **le code
  déployé**, pas une copie.

## 7. Évolutions possibles

- Publier le composant en **package npm** (`@mirai/prompt-guard`) versionné pour
  réutilisation hors de ce repo (registre privé).
- Embarquer le **corpus versionné + tests de régression** dans le package.
- Ajouter un mode **juge en ensemble** (vote multi-modèles) derrière `GuardConfig`.
- **Emprunts à NeMo Guardrails** (analyse comparée :
  [`nemo-guardrails-comparison.md`](./nemo-guardrails-comparison.md)) :
  - ✅ **(a)** Détecteur d'anomalie « proxy de perplexité » (anti-suffixe GCG) dans
    `core.ts` — `anomalyDetector` + intégré à `inspectInput`. Posture par défaut
    **`audit`** (`GuardConfig.anomaly.mode`) : journalise un signal `advisory` sans
    bloquer (le proxy est bruité — code/markup dense le déclenche). Câblé en audit
    sur les routes chat + onboarding. Promouvable en `block` via `GuardConfig`.
  - ✅ **(b)** **Parser keyword de repli** (`parseKeywordVerdict`) dans `judgeWith` :
    avant de fail-closer sur un verdict non-JSON, on tente un mapping yes/no/safe/
    unsafe (FR+EN) → réduit le `failClosedRate`.
  - ✅ **(f)** **Inspecteur de sortie en streaming** (`createStreamingOutputInspector`,
    fenêtre glissante + contexte reporté) — capacité composant, non branchée (app
    en `stream:false`).
  - 🔲 Backlog : **(c)** classifieur dédié type Llama Guard, **(d)** grounding /
    fact-check pour la désinformation, **(e)** détecteur PII en sortie — tous
    derrière `GuardConfig`, en TS pur, sans les dépendances lourdes de NeMo.
