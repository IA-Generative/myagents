// Point d'entrée VITEST du runner de matrice (faute de `tsx` dans le repo, on
// réutilise le runner vitest déjà configuré + le chargement d'.env.test.local).
//
// OPT-IN double : ne s'exécute que si REDTEAM_MATRIX=1 ET credentials présents.
// Sinon skip (npm test reste vert). Lancer via :
//   npm run test:redteam:matrix         (matrice complète, 9 modèles)
//   REDTEAM_SMOKE=1 npm run test:redteam:matrix   (pré-vol 1 modèle × 2 payloads)

import { describe, it, expect } from 'vitest';
import { runMatrix, parseMatrixOptions } from './run-matrix';

const ENABLED = process.env.REDTEAM_MATRIX === '1';
const HAS_CREDS =
  Boolean(process.env.SCW_LLM_BASE_URL) && Boolean(process.env.SCW_SECRET_KEY_LLM);

describe.skipIf(!ENABLED || !HAS_CREDS)('red-team — matrice multi-modèles', () => {
  it(
    'joue le corpus contre les modèles et écrit la synthèse',
    async () => {
      const opts = parseMatrixOptions();
      const { report, paths } = await runMatrix(opts);
      expect(report.records.length).toBeGreaterThan(0);
      // Au moins un résultat exploitable (pas que des erreurs d'appel).
      const usable = report.records.filter((r) => r.outcome !== 'error');
      expect(usable.length).toBeGreaterThan(0);
      console.log(`\nSynthèse écrite : ${paths.md}`);
    },
    // Run long (matrice complète = milliers d'appels). Timeout 2 h.
    7_200_000,
  );
});

if (!ENABLED || !HAS_CREDS) {
  describe('red-team — matrice', () => {
    it.skip('skippé — exporter REDTEAM_MATRIX=1 + credentials Scaleway (.env.test.local)', () => {});
  });
}
