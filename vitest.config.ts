import { defineConfig } from 'vitest/config';
import { resolve } from 'node:path';

// Config Vitest du repo. Deux familles de tests :
//   - tests/redteam/ : red-team (appelle un vrai LLM, opt-in, skip sans creds) ;
//   - tests/routes/  : handlers de routes API (mocks, offline) — nécessitent la
//                      résolution des alias `@/...` (comme tsconfig).
export default defineConfig({
  resolve: {
    // Aligné sur tsconfig paths : `@/app/*` → app/*, `@/*` → src/*.
    // L'ordre compte : `@/app/` doit précéder `@/`.
    alias: [
      { find: /^@\/app\//, replacement: resolve(process.cwd(), 'app') + '/' },
      { find: /^@\//, replacement: resolve(process.cwd(), 'src') + '/' },
    ],
  },
  test: {
    setupFiles: ['tests/redteam/env.setup.ts'],
    testTimeout: 60_000,
    hookTimeout: 60_000,
    // Les tirages LLM sont déjà concurrents au sein d'un test ;
    // on évite de saturer l'API Scaleway en parallélisant aussi les fichiers.
    fileParallelism: false,
  },
});
