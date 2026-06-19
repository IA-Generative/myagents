import { defineConfig } from 'vitest/config';

// Config Vitest du repo. Aujourd'hui seule la suite red-team
// (tests/redteam/) existe : elle appelle un vrai LLM, donc les timeouts
// sont larges (gpt-oss-120b est un modèle "reasoning", lent à répondre).
//
// La suite est OPT-IN : sans credentials Scaleway elle se skip d'elle-même
// (cf. describe.skipIf dans prompt-injection.test.ts), donc `npm test`
// reste vert et hors-ligne par défaut.
export default defineConfig({
  test: {
    setupFiles: ['tests/redteam/env.setup.ts'],
    testTimeout: 60_000,
    hookTimeout: 60_000,
    // Les tirages LLM sont déjà concurrents au sein d'un test ;
    // on évite de saturer l'API Scaleway en parallélisant aussi les fichiers.
    fileParallelism: false,
  },
});
