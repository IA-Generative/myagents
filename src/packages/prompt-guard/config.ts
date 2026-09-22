// @mirai/prompt-guard — CONFIGURATION du composant.
//
// Regroupe les réglages opérationnels : modèle du LLM-juge, couches activées,
// posture fail-closed. Aucune dépendance : la résolution du modèle lit une
// variable d'environnement optionnelle (override) avec repli, sans passer par
// la validation zod de l'app (le composant doit rester réutilisable hors Next).

import { DEFAULT_ANOMALY, type AnomalyConfig } from './core';

export type GuardLayer = 'input' | 'harden' | 'output' | 'judge';

export type GuardConfig = {
  /** Modèle à utiliser pour le LLM-juge. `undefined` → repli sur SCW_LLM_MODEL. */
  judgeModel?: string;
  /** Couches activées (toutes par défaut). */
  layers: Record<GuardLayer, boolean>;
  /** Fail-closed : un juge indisponible/illisible compte comme une compliance. */
  failClosed: boolean;
  /**
   * Détecteur d'anomalie (proxy de perplexité, anti-suffixe GCG). Posture par
   * défaut « audit » : journalise un signal advisory sans bloquer (le détecteur
   * est bruité ; cf. core.ts). Passer `mode: 'block'` pour l'activer en blocage.
   */
  anomaly: AnomalyConfig;
};

/**
 * Modèle juge par défaut, éclairé par le benchmark coût-vs-détection
 * (tests/redteam/judge-eval.ts → reports/judge-eval-*.md).
 *
 * Benchmark des 9 modèles (2026-06-20, jeu de 36 cas étiquetés) :
 *  - `gpt-oss-120b`        : rappel 93 %, précision 100 %, F1 96 %, FPR 0 %,
 *                            **fail-closed 0 %**, latence 1,1 s (coût 4/5).
 *  - `gemma-4-26b-a4b-it`  : rappel 96 %, F1 98 %, FPR 0 % mais **17 % fail-closed**
 *                            (coût 2/5) — le moins cher atteignant les seuils.
 *
 * CHOIX RETENU : `gpt-oss-120b` — privilégie la FIABILITÉ du juge (0 % de verdicts
 * illisibles, donc pas de blocages fail-closed parasites) plutôt que le coût.
 * Override possible via la variable d'env `GUARD_JUDGE_MODEL`.
 */
// ⚠ `gpt-oss-120b` (le nom du benchmark) a été RETIRÉ du catalogue Scaleway le
//   2026-08-25 — renommé `gptoss-120b`, sans tiret. Le juge répondait 400 et la garde,
//   fail-closed, bloquait TOUT. Les noms d'opérateur bougent : en déploiement, préférer
//   la variable GUARD_JUDGE_MODEL, qui se corrige sans reconstruire.
export const RECOMMENDED_JUDGE_MODEL: string | undefined = 'gptoss-120b';

export const DEFAULT_GUARD_CONFIG: GuardConfig = {
  judgeModel: RECOMMENDED_JUDGE_MODEL,
  layers: { input: true, harden: true, output: true, judge: true },
  failClosed: true,
  // Posture produit recommandée : audit (journalise, ne bloque pas).
  anomaly: { ...DEFAULT_ANOMALY, mode: 'audit' },
};

/**
 * Résout le modèle du juge : argument explicite > variable d'env
 * `GUARD_JUDGE_MODEL` > recommandation du benchmark > `undefined` (repli app
 * sur SCW_LLM_MODEL).
 */
export function resolveJudgeModel(explicit?: string): string | undefined {
  return explicit ?? process.env.GUARD_JUDGE_MODEL ?? RECOMMENDED_JUDGE_MODEL;
}
