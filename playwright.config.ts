import { defineConfig } from '@playwright/test';

// E2E red-team : tests HTTP contre l'instance DÉPLOYÉE (auth Keycloak réelle).
// baseURL = E2E_BASE_URL (ex. https://<host-prod>). Un projet `setup` se logue
// via Keycloak et sauvegarde la session ; le projet `e2e` la réutilise.
const BASE = process.env.E2E_BASE_URL ?? 'https://myagents.fake-domain.name';

export default defineConfig({
  testDir: 'tests/e2e',
  timeout: 120_000,
  expect: { timeout: 20_000 },
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [['list'], ['json', { outputFile: 'tests/e2e/.report/results.json' }]],
  use: {
    baseURL: BASE,
    trace: 'retain-on-failure',
    ignoreHTTPSErrors: false,
  },
  projects: [
    { name: 'setup', testMatch: /auth\.setup\.ts/ },
    {
      name: 'e2e',
      testMatch: /.*\.spec\.ts/,
      dependencies: ['setup'],
      use: { storageState: 'tests/e2e/.auth/state.json' },
    },
  ],
});
