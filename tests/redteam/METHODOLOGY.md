# Méthodologie red-team & pistes d'amélioration

Ce document décrit la méthode du banc d'essai red-team et propose des
améliorations pour des campagnes de test équivalentes. Il complète le
[README](./README.md) (lancement, variables) et la synthèse produite dans
`reports/`.

## 1. Deux rôles distincts à évaluer

Le même modèle joue deux rôles qu'il faut **mesurer séparément** :

| Rôle | Question | Outil |
| --- | --- | --- |
| **Cible** | Le modèle résiste-t-il à l'attaque ? | `run-matrix.ts` (surfaces *brut* / *gardé*) |
| **Juge** | Détecte-t-il qu'une réponse a cédé ? | `judge-eval.ts` (jeu étiqueté) |

Mélanger les deux (juger une cible avec elle-même) masque les faiblesses. La
matrice mesure la robustesse ; le benchmark de juge mesure la fiabilité du
détecteur LLM et **choisit le modèle juge** du module (coût vs détection).

## 2. Trois surfaces de mesure

- **Cible brute** : modèle nu (system prompt bénin). Mesure la robustesse
  *intrinsèque* — utile pour choisir un modèle de production sûr par défaut.
- **Cible derrière la garde** : pipeline de production réel (inspectInput →
  hardenSystemPrompt → inspectOutput → juge). Mesure la sécurité *bout-en-bout*.
  Un breach ici = **fuite que la garde a manquée** (priorité de correction).
- **Couche déclenchante** : pour chaque blocage gardé, on trace si c'est l'entrée
  (couche 1) ou la sortie (couche 3) qui a stoppé — révèle quelle couche porte
  la défense pour chaque famille d'attaque.

## 3. Reproductibilité

- **Température** : épingler (0 pour le juge ; pour la cible, 0 donne un
  worst-case déterministe, > 0 explore la variance). Aujourd'hui la cible utilise
  le défaut serveur — préférer une valeur fixée et tracée par run.
- **Échantillonnage** : `REDTEAM_SAMPLES` tirages par cellule (worst-case : un
  seul tirage qui cède suffit à marquer un breach). Augmenter pour stabiliser le
  *taux* de breach (vs le booléen worst-case).
- **Version de modèle** : tracer l'`id` exact (Scaleway peut mettre à jour un
  alias). Idéalement logguer l'empreinte de la réponse `/models`.

## 4. Rigueur statistique

- Distinguer **worst-case** (a-t-il cédé au moins une fois ?) et **taux** (sur N
  tirages) — la synthèse rapporte le taux ; pour un go/no-go, le worst-case prime.
- Pour N petit, donner un **intervalle de confiance** (Wilson) plutôt qu'un
  pourcentage brut.
- **Couverture par axe** : la synthèse ventile par technique ZORG (`axes`) ; viser
  un nombre minimal de tirages par axe pour des comparaisons valides.

## 5. Contrôle des faux positifs (FPR)

Une garde qui bloque du contenu légitime est un défaut aussi grave qu'une fuite.
Le benchmark de juge inclut des **cas bénins** (réponses neutres/factuelles,
refus polis, code propre) et mesure le **FPR**. À étendre :

- jeu de contrôle bénin côté *matrice* (prompts administratifs réalistes) pour
  mesurer le taux de blocage à tort de `inspectInput`/`inspectOutput` ;
- suivi du FPR dans le temps (régression).

## 6. Artefacts persistés & baseline de régression

- Chaque run écrit `results-*.json` (brut), `summary-*.csv` (agrégé),
  `synthesis-*.md` (lisible). Conserver les `.md`/`.csv` comme **baseline**.
- Comparer deux runs (avant/après changement de garde ou de modèle) et **alerter
  sur les régressions** (nouvelle fuite, FPR en hausse). Un petit script de diff
  CSV peut gater une PR.

## 7. Élargir la surface d'attaque

Le corpus actuel couvre l'injection directe (user) et la chaîne
d'approvisionnement (system). Pistes :

- **Injection indirecte / RAG** : payload caché dans un document récupéré ou une
  sortie d'outil (le vecteur OWASP LLM01 le plus réaliste en production).
- **Multilingue** : déjà FR + EN dans ZORG ; ajouter d'autres langues et le
  *code-switching* (mélange de langues dans un même prompt).
- **Obfuscation unicode** : homoglyphes, caractères zéro-largeur, RTL override,
  variations de casse/espaces — au-delà du hex/base64 actuels.
- **Multi-tours** : escalade progressive sur plusieurs messages, *payload
  splitting* (l'attaque répartie sur plusieurs tours pour passer sous le radar).
- **Chaînes d'encodage** : base64 → rot13 → hex imbriqués ; demande de décodage
  en plusieurs étapes.
- **Suffixes adversariaux (GCG)** : suffixe optimisé sans mot-clé, invisible aux
  regex. Détectable par **perplexité** (cf. NeMo : `len/perplexité`, perplexité
  préfixe/suffixe) — piste de détecteur complémentaire dans `core.ts`.

Chaque nouvelle famille s'ajoute soit à `payloads.ts` (cas figés), soit comme
nouvel axe paramétré du générateur `zorg-corpus.ts`.

> **Inspirations externes** : l'analyse comparée de **NVIDIA NeMo Guardrails**
> (détection par perplexité, parser self-check robuste, grounding/fact-check,
> rails en streaming) et les améliorations actionnables qui en découlent sont
> documentées dans [`docs/nemo-guardrails-comparison.md`](../../docs/nemo-guardrails-comparison.md).

## 8. Durcir le scoring

- **Juge en ensemble** : faire voter plusieurs modèles juges (ou N appels d'un
  même juge à température > 0) et décider à la majorité — réduit le bruit du juge.
- **Vérification adversariale** : sur les breaches détectés, un second juge
  cherche à *réfuter* le verdict (réduit les faux breaches du juge).
- **Fail-closed** : conservé (un verdict illisible compte comme une compliance) —
  à garder, mais suivre le `failClosedRate` (un juge souvent illisible est
  inutilisable même s'il « attrape tout »).

## 9. Coût & CI

- La matrice complète (milliers d'appels) reste **manuelle** (coût/flakiness).
- Proposer un **smoke gardé en CI** : 1 modèle, sous-corpus, `REDTEAM_SMOKE=1`,
  avec plafond de budget — détecte une régression franche sans coût prohibitif.
- Réglages de coût : `REDTEAM_MODELS` (sous-ensemble), `REDTEAM_SAMPLES`,
  `REDTEAM_CONCURRENCY`, `REDTEAM_CORPUS=baseline|zorg|all`,
  `REDTEAM_SURFACES=raw|guarded|both`.
- Coût absolu : la synthèse rapporte tokens + *coût relatif* (palier `models.ts`).
  Pour des euros, brancher une table de prix Scaleway (€/Mtoken) — non versionnée
  ici (susceptible de changer).

## 10. Ajouter une campagne équivalente

1. Définir les **objectifs mesurables** (un détecteur déterministe ou un `goal`
   clair pour le juge). Éviter de générer du contenu réellement nocif : préférer
   des cibles inertes et détectables (cf. keylogger / fausses sources / fuite).
2. Décrire les **axes** de variation et les générer (`zorg-corpus.ts` comme
   gabarit) plutôt que d'écrire les payloads à la main.
3. Lancer la matrice, lire `synthesis-*.md` (tableaux A–E), corriger les fuites,
   re-lancer (baseline de régression).
