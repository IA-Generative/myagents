// Validation des variables d'environnement avec zod — fail-fast au démarrage.
// Toutes les variables serveur sont lues ici, jamais directement via process.env
// ailleurs dans le code.

import { z } from 'zod';

const serverSchema = z.object({
  NODE_ENV: z.enum(['development', 'test', 'production']).default('development'),

  // Upstream OpenWebUI (BFF proxy)
  OWUI_BASE_URL: z.string().url(),

  // Keycloak / OIDC
  KEYCLOAK_ISSUER: z.string().url(),
  KEYCLOAK_CLIENT_ID: z.string().min(1),
  KEYCLOAK_CLIENT_SECRET: z.string().min(1),

  // NextAuth
  NEXTAUTH_URL: z.string().url(),
  NEXTAUTH_SECRET: z.string().min(1),

  // PostgreSQL (Prisma)
  DATABASE_URL: z.string().min(1),

  // --- Scaleway Generative APIs (LLM souverain) ---
  // Optionnels : si absents, les endpoints /api/ab/prompt/assist et /optimize
  // renvoient 501 Not Implemented. Nom des vars aligné sur owuicore-main/.env
  // pour pouvoir réutiliser le même Secret K8s (`owui-socle-secrets`).
  SCW_LLM_BASE_URL: z.string().url().optional(),
  SCW_SECRET_KEY_LLM: z.string().optional(),
  SCW_LLM_MODEL: z.string().default('gpt-oss-120b'),

  // URL publique d'OpenWebUI (MirAI Chat) pour le bouton "Poursuivre dans MirAI Chat"
  OWUI_PUBLIC_URL: z.string().url().optional(),

  // Cle API admin OpenWebUI pour creer/supprimer des modeles via /api/v1/models/create
  OWUI_ADMIN_API_KEY: z.string().optional(),

  // Restriction d'acces a un groupe du realm. Optionnel : non renseigne, tout
  // utilisateur du realm entre — c'est le comportement historique. Renseigne,
  // seuls les membres du groupe nomme sont admis (claim `groups` de l'ID token).
  OIDC_GROUPE_EXIGE: z.string().optional(),
});

export type ServerEnv = z.infer<typeof serverSchema>;

function parseEnv(): ServerEnv {
  // Pendant `next build`, les secrets runtime ne sont pas disponibles
  // (ils seront injectés au démarrage du conteneur). Next.js fait un
  // static-analysis des routes API qui importe tout le graphe de modules,
  // donc on ne peut pas strictement valider ici sans casser le build.
  // SKIP_ENV_VALIDATION=1 est exporté dans le Dockerfile stage builder.
  if (process.env.SKIP_ENV_VALIDATION === '1') {
    return {
      NODE_ENV: 'production',
      OWUI_BASE_URL: 'http://build-placeholder',
      KEYCLOAK_ISSUER: 'https://build-placeholder/realms/build',
      KEYCLOAK_CLIENT_ID: 'build-placeholder',
      KEYCLOAK_CLIENT_SECRET: 'build-placeholder',
      NEXTAUTH_URL: 'http://build-placeholder',
      NEXTAUTH_SECRET: 'build-placeholder',
      DATABASE_URL: 'postgresql://build:build@build/build',
      SCW_LLM_BASE_URL: undefined,
      SCW_SECRET_KEY_LLM: undefined,
      SCW_LLM_MODEL: 'gpt-oss-120b',
      OWUI_PUBLIC_URL: undefined,
      OWUI_ADMIN_API_KEY: undefined,
      OIDC_GROUPE_EXIGE: undefined,
    };
  }

  const parsed = serverSchema.safeParse(process.env);
  if (!parsed.success) {
    // On liste les variables manquantes de manière lisible pour faciliter
    // le diagnostic dans les logs K8s.
    const issues = parsed.error.issues
      .map((i) => `  - ${i.path.join('.')}: ${i.message}`)
      .join('\n');
    throw new Error(
      `Configuration invalide — variables d'environnement manquantes ou mal formées:\n${issues}`,
    );
  }
  return parsed.data;
}

// Lazy singleton pour éviter d'échouer à l'import côté client (Next.js
// compile certains modules serveur dans le bundle client : env est donc
// lu uniquement quand une fonction serveur l'appelle).
let cached: ServerEnv | undefined;
export function env(): ServerEnv {
  if (!cached) {
    cached = parseEnv();
  }
  return cached;
}
