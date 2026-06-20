# Note technique — NeMo Guardrails vs `@mirai/prompt-guard`

> Comparaison du framework **NVIDIA NeMo Guardrails (v0.21)** avec notre module **`@mirai/prompt-guard`** (TypeScript, MirAI Agent Builder), et améliorations actionnables qui en découlent.
> Module concerné : `src/packages/prompt-guard/{core,judge,config}.ts` — banc d'essai : `tests/redteam/`.
> Analyse réalisée par lecture du dépôt NeMo local (`/Users/etiquet/Documents/GitHub/Guardrails`, v0.21), 8 sous-systèmes.

---

## NeMo Guardrails en bref

NeMo Guardrails est un framework Python de garde **déclaratif** posé autour d'un LLM principal. Son architecture repose sur trois piliers.

**1. Des rails typés, exécutés en pipeline.** Chaque appel traverse une séquence de rails, chacun étant un point de contrôle qui peut altérer le contexte ou interrompre (`abort`) :

- `input rails` — sur le message utilisateur (avant génération) ;
- `dialog rails` — sur l'intention / le sujet (topical) ;
- `retrieval rails` — sur les chunks RAG injectés ;
- `output rails` — sur la réponse du bot (après génération, avec un mode **streaming** : `chunk_size≈200` tokens, `context_size≈50` reportés, `stream_first`) ;
- `tool_input` / `tool_output rails` — autour des appels d'outils.

Les rails sont **paramétrés en YAML** (`rails.input.flows`, `rails.output.flows`, drapeau `parallel` par type) et peuvent s'exécuter de façon spéculative en parallèle de la génération pour masquer la latence.

**2. Colang, un DSL de flux de dialogue.** Les rails sont écrits en Colang (`.co`), un langage de scénario qui gère des variables de contexte (`$user_message`, `$bot_message`, `$relevant_chunks`, `$check_facts`) et orchestre `await Action(...)` → `if result then abort`. C'est le « ciment » qui compose les détecteurs et conditionne leur déclenchement (*context-variable gating* : poser `$check_facts` avant émission pour activer un rail).

**3. Le pattern self-check / dual-LLM (« LLM-as-judge »).** Le moteur de vérification central est un LLM interrogé avec un prompt task-spécifique (taxonomie + format de sortie contraint), à **température quasi nulle** (`lowest_temperature = 0.001`, parfois `1e-20`), dont la réponse est parsée par un *output parser* robuste (`is_content_safe` : normalisation `\W+→espace`, lecture des 2 premiers tokens, lookup `safe/unsafe/yes/no`, **fail-closed** sur réponse vide/inconnue). NeMo permet une **composition multi-LLM** : un modèle généraliste pour la génération + des modèles spécialisés comme juges (jailbreak detector ONNX, content-safety Llama Guard, AlignScore fact-checker).

**Positionnement.** NeMo est un *framework* généraliste, configurable, à large surface (PII, fact-checking, topical, streaming, classifieurs dédiés), au prix d'une dépendance Python lourde (spaCy, transformers, ONNX, YARA, Presidio) et de la courbe d'apprentissage de Colang. Notre `prompt-guard` est un *composant* TypeScript minimal, sans dépendance hors `node:crypto`, ciblé sur un périmètre précis (OWASP LLM01) et trois objectifs mesurables (keylogger, désinformation/fausses sources, fuite de prompt).

---

## Comparaison avec notre prompt-guard

| Capacité | NeMo Guardrails | `@mirai/prompt-guard` | Écart |
| --- | --- | --- | --- |
| **Détection d'injection (patterns)** | Règles YARA compilées (`sqli`, `code`, `xss`, `template`) : mots-clés SQL (`SELECT/DROP/UNION/-- //* */`), imports Python (`os/subprocess/socket/requests`) avec contraintes d'ordre `@offset`, XSS (`<script>`, `javascript:`, embeds markdown), Jinja2 (`{{ }}`, `{% %}`). Actions `reject`/`omit`/`sanitize`. | `INJECTION_MARKERS` : ~10 regex FR/EN (`ignore previous instructions`, mode dév, DAN, exfiltration de system prompt, base64, fausses sources) + `KEYLOGGER_SIGNATURES` (6 signatures JS) avec `deobfuscate()` (hex `\xNN`, concat de chaînes). Blocage strict. | NeMo couvre SQL/XSS/template/code que nous n'avons pas. Nous couvrons des marqueurs **sémantiques FR** que NeMo n'a pas. Tous deux : regex case-insensitive, pas de fuzzy. |
| **Jailbreak par perplexité** | Heuristique GPT-2 : `score = len/perplexity` (seuil **89.79**) + perplexité préfixe/suffixe (19 premiers/derniers tokens, seuil **1845.65**, détecte GCG) ; ignore < 20 mots. + classifieur ONNX (Snowflake embed 384-d + Random Forest). | **Aucune.** Détection purement par mots-clés. | **Écart net.** Nous sommes contournables par suffixe adversarial (GCG) que la perplexité attrape sans mot-clé. |
| **Self-check LLM** | `self_check_input/output/facts` : prompt taxonomie + `temp 0.001`, parser `is_content_safe`, inversion `output_mapping` (yes=block), fail-closed, `max_tokens 1024`, strip `<think>`. | `judgeWith` (`judge.ts`) : juge inline binaire `{complied, reason}`, `temp 0`, `maxTokens 512`, parsing JSON fail-closed. **Mono-appel**, pas d'ensemble. | Convergent sur l'esprit (temp basse + fail-closed). NeMo apporte le parser keyword-robuste et le multi-pass ; nous, un JSON structuré plus simple. |
| **Classifieur dédié (Llama Guard)** | `content_safety` / `llama_guard` : modèles dédiés, taxonomie O1–O7, format contraint (1re ligne `safe/unsafe`, 2e ligne catégories), cache par hash normalisé, dispatch multilingue. | **Aucun.** Notre seul « classifieur » est le LLM-juge généraliste `gpt-oss-120b`. | Écart de couverture (catégories) ; mais un classifieur dédié = dépendance/modèle en plus, hors périmètre actuel. |
| **Fact-checking / grounding** | `factchecking/align_score` (RoBERTa NLI, score 0-1, seuil 0.5) + `self_check_facts` (LLM « entails ? ») + `hallucination` self-consistency (2 complétions `temp=1.0` + LLM agreement). | Notre objectif « désinformation » repose **uniquement** sur le juge LLM jugeant « a-t-il inventé des sources ? » — **sans evidence / sans grounding**. | Écart réel sur le *grounding* (comparaison à des preuves). Notre détection est intentionnelle (fausses sources), pas factuelle au sens NLI. |
| **PII / données sensibles** | `sensitive_data_detection` (Presidio + spaCy `en_core_web_lg` 768 Mo) : entités `PERSON/EMAIL/SSN/...`, `score_threshold` configurable, modes **detect** (bool) ou **mask** (`<ENTITY>`). | **Aucune.** | Écart total — mais hors périmètre LLM01, et dépendance lourde (spaCy/Presidio). |
| **Rails topical / dialogue** | `dialog rails` + `topic_safety_check_input` (LLM `temp 0.01`, `max_tokens 10`, on-topic/off-topic, cache LFU) + `context_bloat_detection` (entropie de Shannon, longest-run-ratio, n-gram repetition). | **Aucun** rail topical ni anti-bloat. | Écart ; pertinent surtout si dérive de sujet/abus = menace (pas notre cible n°1). L'anti-bloat est un radar orthogonal intéressant. |
| **Streaming output rails** | Oui : filtrage par fenêtre glissante (`chunk_size`, `context_size`, `stream_first`). | **Non** : `inspectOutput` opère sur la réponse **complète**. | Écart UX/latence si on stream les réponses ; sinon non bloquant. |
| **Masquage vs blocage** | Les deux : `omit`/`sanitize` (injection), `mask` PII (`<ENTITY>`), `truncate` (bloat). | **Blocage uniquement** (3 messages sobres : input user / config agent / output). | Choix assumé (faux positif > compliance). Le masquage serait une option, pas un défaut. |
| **Orchestration / DSL** | Colang (`.co`) + config YAML déclarative, gating par variable de contexte, exécution parallèle/spéculative. | Composition **en code TS** : `inspectInput → hardenSystemPrompt → inspectOutput → judgeWith`, couches activables via `GuardConfig.layers` (`config.ts`). | NeMo plus flexible/déclaratif ; nous plus simple, typé, testable, sans runtime à apprendre. |

---

## Ce que nous pouvons emprunter (priorisé)

### (a) Détection jailbreak par perplexité (length-per-perplexity) — *complément regex*
- **Quoi** : ajouter un détecteur statistique léger dans `core.ts` : `score = longueur / perplexité` (seuil de départ **89.79**) + perplexité préfixe/suffixe (19 premiers/derniers tokens, seuil **1845.65**), en ignorant les entrées < 20 mots. Pas besoin d'un LLM complet : une tokenization + un n-gram model léger (ou un wrapper WASM) suffit pour un *signal d'anomalie*.
- **Pourquoi** : nos regex sont contournables par suffixe adversarial (GCG) qui ne contient aucun mot-clé. La perplexité capte la « densité de tokens aléatoires » qu'aucun marqueur ne verra.
- **Effort** : moyen (implémenter/embarquer un scoring de perplexité côté Node).
- **Impact** : élevé sur les attaques par suffixe optimisé ; faible coût/latence en première passe.
- **Intégration** : nouveau `Signal` `source: 'perplexity'` dans `inspectInput` (`core.ts`), seuils paramétrables via `GuardConfig` (`config.ts`). Ajouter un axe « suffixe GCG / bruit adversarial » à `tests/redteam/zorg-corpus.ts` et **calibrer les seuils sur notre corpus** (suivre FPR/FNR — cf. METHODOLOGY §5). Documenter dans `tests/redteam/METHODOLOGY.md §7` (déjà listé comme piste « obfuscation »).

### (b) Prompts self-check NeMo — *alternative/complément au LLM-juge*
- **Quoi** : durcir le parsing de `judgeWith` (`judge.ts`) en s'inspirant de `is_content_safe` : fallback keyword (normaliser `\W+→espace`, lire les 2 premiers tokens `yes/no/safe/unsafe`) **quand le JSON est illisible**, au lieu de fail-closer directement. Optionnellement, offrir une variante de prompt « company-policy bullets + Question: Should be blocked? (Yes/No) » comme second format.
- **Pourquoi** : aujourd'hui un verdict non-JSON → fail-closed (faux blocage). Le benchmark montre que `gpt-oss-120b` a 0 % fail-closed mais `gemma` 17 % : un parser tolérant récupère ces cas sans relâcher la sécurité (le fallback reste fail-closed *in fine*).
- **Effort** : faible.
- **Impact** : moyen — réduit le `failClosedRate` (faux positifs) sans baisser le rappel.
- **Intégration** : enrichir le bloc `match`/`JSON.parse` de `judgeWith` (`judge.ts`) avec un `parseKeywordVerdict()` de repli **avant** le `complied: true` final. Couvrir par `tests/redteam/judge-eval.ts` (mesurer l'effet sur FPR et fail-closed rate).

### (c) Classifieur dédié type Llama Guard / content-safety — *en option*
- **Quoi** : permettre de brancher un classifieur de sécurité dédié (Llama Guard ou équivalent souverain) derrière l'interface `LLMJudge`, avec taxonomie de catégories et format contraint (1re ligne `safe/unsafe`, 2e ligne catégories), validé contre une whitelist de catégories.
- **Pourquoi** : un modèle dédié est plus robuste qu'un juge généraliste sur les catégories standard et sort des *catégories* exploitables pour le triage/audit.
- **Effort** : élevé (déployer/héberger un modèle dédié sur Scaleway souverain).
- **Impact** : moyen — gain marginal vu nos 3 objectifs déjà bien couverts par `gpt-oss-120b` ; surtout utile si on élargit le périmètre.
- **Intégration** : nouvelle implémentation de l'interface `LLMJudge` (`judge.ts`) + entrée `judgeModel`/mode dans `GuardConfig` (`config.ts`). À **benchmarker contre le juge actuel** via `tests/redteam/judge-eval.ts` avant toute adoption (la barre est `gpt-oss-120b` : F1 96 %, FPR 0 %).

### (d) Grounding / fact-check pour l'objectif désinformation
- **Quoi** : pour la cible « fausses sources », ajouter une vérification de *grounding* optionnelle : quand des `relevant_chunks`/evidence existent (RAG), demander au juge « l'affirmation est-elle étayée par ces preuves ? (yes/no) » (pattern `self_check_facts`, seuil 0.5), avec fallback LLM si pas de modèle NLI.
- **Pourquoi** : aujourd'hui notre détection « invente des sources » est *intentionnelle* (le juge lit la consigne malveillante), pas *factuelle*. Le grounding attrape la désinformation même sans consigne explicite.
- **Effort** : moyen (uniquement pertinent si/quand un contexte RAG est disponible).
- **Impact** : moyen-élevé sur l'objectif désinformation en présence de sources.
- **Intégration** : nouveau `goal` dédié + paramètre `evidence` optionnel dans `judgeWith` (`judge.ts`) ; nouvel axe « claim vs evidence » dans `tests/redteam/zorg-corpus.ts`. À relier à la piste « Injection indirecte / RAG » déjà notée en `METHODOLOGY.md §7`.

### (e) PII / sensitive-data — *en option*
- **Quoi** : détecteur PII optionnel en sortie (`inspectOutput`), soit par regex ciblées (email, NIR/SSN, téléphone, IBAN), soit via un service externe type Presidio si jamais requis, avec mode **detect** (bloque) ou **mask** (`<ENTITY>`).
- **Pourquoi** : couvre la *fuite* de PII après injection — complémentaire, pas concurrent, de notre détection d'injection en amont.
- **Effort** : faible (regex) à élevé (Presidio/spaCy 768 Mo — à éviter).
- **Impact** : faible sur notre périmètre actuel (LLM01), à activer si une exigence RGPD/SecNumCloud l'impose.
- **Intégration** : nouveau `Signal` `source: 'pii'` dans `inspectOutput` (`core.ts`), désactivé par défaut dans `GuardConfig.layers`. **Privilégier des regex pures** pour rester sans dépendance lourde (cf. section suivante).

### (f) Output rails en streaming — *idée*
- **Quoi** : si on passe les réponses en streaming, filtrer par fenêtre glissante (chunk + contexte reporté) plutôt que d'attendre la réponse complète, avec re-scan des détecteurs sortie (keylogger, canari).
- **Pourquoi** : éviter d'afficher du contenu interdit token par token avant le verdict final ; améliorer la latence perçue.
- **Effort** : moyen-élevé (dépend de l'architecture de streaming côté Next).
- **Impact** : faible aujourd'hui (sortie inspectée en bloc), élevé si le streaming devient le défaut UX.
- **Intégration** : variante streaming de `inspectOutput` (`core.ts`) opérant sur des fragments + état (contexte reporté). À cadrer avant implémentation — non prioritaire.

---

## Ce que NeMo fait que nous évitons volontairement

- **Surface fonctionnelle massive** (PII, fact-checking NLI, topical, bloat, streaming, multi-classifieurs). Notre périmètre est borné à **OWASP LLM01** avec 3 objectifs *mesurables* (keylogger, fausses sources, fuite de prompt). Élargir diluerait la testabilité et le signal du banc d'essai.
- **Dépendances Python lourdes** : spaCy `en_core_web_lg` (768 Mo), transformers/GPT-2, ONNX runtime, Presidio, `yara-python`, `fast-langdetect`. Notre `core.ts` ne dépend que de `node:crypto` — c'est une **source de vérité partagée** entre la production (`src/lib/prompt-guard.ts`) et le harnais red-team, déployable partout, auditable d'un coup d'œil. Embarquer ces modèles casserait cette propriété.
- **Complexité de Colang** : un DSL de flux + runtime à apprendre, debugger et versionner. Notre orchestration est du **TypeScript typé linéaire** (`inspectInput → hardenSystemPrompt → inspectOutput → judgeWith`), couvert par des tests unitaires, sans moteur d'exécution opaque. Pour un pipeline à 3 couches, le code l'emporte sur le DSL.
- **Classifieurs/modèles supplémentaires à héberger** : chaque modèle dédié (Llama Guard, AlignScore, RF ONNX) = un service souverain de plus à opérer et homologuer. Notre juge unique `gpt-oss-120b` (Scaleway souverain) couvre déjà nos objectifs (F1 96 %, FPR 0 %).

> Conclusion de cette section : notre approche minimale TS reste pertinente parce que **le périmètre est étroit et mesurable**. Les emprunts ci-dessus sont ciblés (perplexité, parsing robuste, grounding optionnel) et n'introduisent pas la surface ni les dépendances de NeMo.

---

## Avertissements / faux amis

- **Les regex (les nôtres comme les YARA de NeMo) sont contournables.** Casse, homoglyphes, caractères zéro-largeur, RTL override, *payload splitting* multi-tours, chaînes d'encodage imbriquées (base64→rot13→hex) passent sous un matching exact. Notre `deobfuscate()` ne couvre que hex + concat ; ne pas surestimer sa portée (cf. pistes `METHODOLOGY.md §7`). Un détecteur n'est jamais une preuve d'attaque — d'où la posture stricte assumée (faux positif > compliance).
- **La perplexité est bruitée.** Seuils NeMo (`89.79`, `1845.65`) calibrés sur dataset NVIDIA, **EN, GPT-2** : ~7,4 % de FP rapportés sur le score length/perplexity. Sur du **français**, du code légitime, des prompts courts ou très techniques, le taux de faux positifs peut exploser. À traiter comme **signal additionnel**, jamais comme blocage seul, et à **recalibrer sur notre corpus** avant activation (FPR vs FNR par axe).
- **Dépendances lourdes = coût caché.** spaCy/Presidio/ONNX/transformers alourdissent l'image, la surface d'attaque (CVE transitives), et le temps de démarrage. Porter une *capacité* (ex. perplexité, patterns SQL/XSS) en TS pur est préférable à importer la *dépendance*.
- **Le coût LLM des self-checks est réel.** Chaque rail self-check = un appel LLM (tokens + latence + flakiness). Multiplier les juges (ensemble, multi-pass, content-safety + fact-check + topical) multiplie le coût. Notre banc d'essai garde la matrice complète **manuelle** et propose un *smoke gardé* plafonné en CI (`METHODOLOGY.md §9`). Tout nouvel appel LLM (grounding, classifieur dédié) doit être **benchmarké coût-vs-détection** avant adoption (`tests/redteam/judge-eval.ts`).
- **Fail-closed ≠ gratuit.** Compter un verdict illisible comme une compliance évite les fuites mais génère des **faux blocages**. À surveiller via le `failClosedRate` : un juge souvent illisible est inutilisable même s'il « attrape tout » (`config.ts` documente déjà ce critère dans le choix `gpt-oss-120b` vs `gemma`).
