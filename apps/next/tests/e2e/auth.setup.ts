// Auth e2e : login Keycloak RÉEL (compte de test) → sauvegarde de la session.
// Identifiants : env E2E_KC_USER/E2E_KC_PASS, sinon private/testkc.txt
// (ligne 1 = identifiant, ligne 2 = mot de passe). JAMAIS committé.

import { test as setup, expect } from '@playwright/test';
import { readFileSync, mkdirSync } from 'node:fs';
import { resolve } from 'node:path';

const STATE = 'tests/e2e/.auth/state.json';

function creds(): { user: string; pass: string } {
  if (process.env.E2E_KC_USER && process.env.E2E_KC_PASS) {
    return { user: process.env.E2E_KC_USER, pass: process.env.E2E_KC_PASS };
  }
  const lines = readFileSync(resolve(process.cwd(), 'private/testkc.txt'), 'utf8')
    .split('\n')
    .map((s) => s.trim())
    .filter(Boolean);
  return { user: lines[0], pass: lines[1] };
}

setup('authenticate via Keycloak', async ({ page }) => {
  const { user, pass } = creds();
  mkdirSync('tests/e2e/.auth', { recursive: true });

  await page.goto('/sign-in');
  await page.getByRole('button', { name: /se connecter avec keycloak/i }).click();

  // Page de login Keycloak (formulaire standard #username / #password / #kc-login).
  await page.locator('#username').waitFor({ state: 'visible', timeout: 30_000 });
  await page.locator('#username').fill(user);
  await page.locator('#password').fill(pass);
  await page.locator('#kc-login, button[type=submit], input[type=submit]').first().click();

  // Retour authentifié sur l'app (callbackUrl '/agents').
  await page.waitForURL(/\/agents(\b|\/|$)/, { timeout: 30_000 });

  // Sanity : la session NextAuth expose bien user.id.
  const res = await page.request.get('/api/auth/session');
  const body = await res.json().catch(() => ({}));
  expect(body?.user?.id, 'session NextAuth doit contenir user.id').toBeTruthy();

  await page.context().storageState({ path: STATE });
});
