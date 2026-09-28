// Point d'entrée VITEST du benchmark de juge (cf. matrix.run.test.ts).
//
// OPT-IN double : REDTEAM_JUDGE=1 ET credentials présents. Lancer via :
//   npm run test:redteam:judge

import { describe, it, expect } from 'vitest';
import { runJudgeEval, parseJudgeOptions, LABELED_SET } from './judge-eval';

const ENABLED = process.env.REDTEAM_JUDGE === '1';
const HAS_CREDS =
  Boolean(process.env.SCW_LLM_BASE_URL) && Boolean(process.env.SCW_SECRET_KEY_LLM);

describe.skipIf(!ENABLED || !HAS_CREDS)('red-team — benchmark du LLM-juge', () => {
  it(
    'évalue les modèles comme juge et écrit le classement coût vs détection',
    async () => {
      const { metrics, paths, recommendation } = await runJudgeEval(parseJudgeOptions());
      expect(metrics.length).toBeGreaterThan(0);
      expect(LABELED_SET.length).toBeGreaterThanOrEqual(12);
      console.log(`\nBenchmark juge écrit : ${paths.md}`);
      console.log(`Recommandé : ${recommendation.best?.model ?? 'n/a'}`);
    },
    3_600_000,
  );
});

if (!ENABLED || !HAS_CREDS) {
  describe('red-team — benchmark du juge', () => {
    it.skip('skippé — exporter REDTEAM_JUDGE=1 + credentials Scaleway (.env.test.local)', () => {});
  });
}
