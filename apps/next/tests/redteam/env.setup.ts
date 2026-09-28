// Setup Vitest pour la suite red-team.
//
// Problème : la cible des attaques est `scwChatCompletions()`, qui importe
// `env()` (src/lib/env.ts). `env()` valide EN DUR plusieurs variables non-LLM
// (OWUI_BASE_URL, KEYCLOAK_*, NEXTAUTH_*, DATABASE_URL) et jette si elles
// manquent — alors qu'on n'en a aucun besoin pour taper le LLM.
//
// Solution : on pose des valeurs FACTICES pour ces variables non-LLM, sans
// jamais écraser une vraie valeur déjà présente dans l'environnement. Les
// seules variables réelles requises sont SCW_LLM_BASE_URL / SCW_SECRET_KEY_LLM
// (typiquement chargées depuis .env.test.local, gitignoré).
//
// IMPORTANT : ne PAS utiliser SKIP_ENV_VALIDATION=1 — cela forcerait
// SCW_LLM_BASE_URL/SCW_SECRET_KEY_LLM à `undefined` et la cible lèverait
// ScwLlmUnavailableError au lieu d'appeler le modèle.

// Charge .env.test.local si présent (sans dépendance externe : lecture best-effort).
// dotenv n'est pas une dépendance du repo, donc on lit le fichier à la main.
import { existsSync, readFileSync } from 'node:fs';
import { resolve } from 'node:path';

function loadEnvFile(relativePath: string): void {
  const path = resolve(process.cwd(), relativePath);
  if (!existsSync(path)) return;
  const content = readFileSync(path, 'utf8');
  for (const rawLine of content.split('\n')) {
    const line = rawLine.trim();
    if (!line || line.startsWith('#')) continue;
    const eq = line.indexOf('=');
    if (eq === -1) continue;
    const key = line.slice(0, eq).trim();
    let value = line.slice(eq + 1).trim();
    // Retire d'éventuels guillemets entourants.
    if (
      (value.startsWith('"') && value.endsWith('"')) ||
      (value.startsWith("'") && value.endsWith("'"))
    ) {
      value = value.slice(1, -1);
    }
    // On n'écrase jamais une variable déjà définie dans l'environnement réel.
    if (process.env[key] === undefined) {
      process.env[key] = value;
    }
  }
}

// Credentials réels (s'ils existent) d'abord.
loadEnvFile('.env.test.local');

// Valeurs factices pour les variables non-LLM exigées par env() — uniquement
// si absentes, pour ne pas masquer une config réelle.
const PLACEHOLDERS: Record<string, string> = {
  NODE_ENV: 'test',
  OWUI_BASE_URL: 'http://redteam-placeholder.invalid',
  KEYCLOAK_ISSUER: 'https://redteam-placeholder.invalid/realms/test',
  KEYCLOAK_CLIENT_ID: 'redteam-placeholder',
  KEYCLOAK_CLIENT_SECRET: 'redteam-placeholder',
  NEXTAUTH_URL: 'http://redteam-placeholder.invalid',
  NEXTAUTH_SECRET: 'redteam-placeholder',
  DATABASE_URL: 'postgresql://redteam:redteam@redteam-placeholder.invalid/redteam',
};

for (const [key, value] of Object.entries(PLACEHOLDERS)) {
  if (process.env[key] === undefined) {
    process.env[key] = value;
  }
}
