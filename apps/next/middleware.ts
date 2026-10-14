// Middleware NextAuth — force le SSO Keycloak sur TOUTES les routes applicatives.
//
// Routes publiques (liste blanche) :
//   - /sign-in            page de connexion elle-même
//   - /api/auth/*         endpoints NextAuth (callback OIDC, CSRF, ...)
//   - /api/health         readiness probe K8s (jamais protégé, sinon le pod
//                         est marqué NotReady avant même d'avoir pu recevoir
//                         une session)
//   - /_next/*, /favicon  assets Next.js (gérés par le matcher plus bas)
//
// Tout le reste (pages et API BFF) est refusé sans JWT NextAuth valide :
//   - pour les pages → redirect vers /sign-in
//   - pour les API   → 401 JSON (géré par withAuth)

import { withAuth } from 'next-auth/middleware';

export default withAuth({
  pages: {
    signIn: '/sign-in',
  },
});

// Le matcher exclut :
//   - /api/auth/*     (NextAuth lui-même — sinon boucle infinie)
//   - /api/health     (probes K8s publiques)
//   - /api/ab/*       (BFF — chaque route a son propre getServerSession qui
//                      renvoie 401 JSON, meilleure UX que 307 HTML pour
//                      les clients fetch). Les routes restent strictement
//                      protégées, juste par un autre mécanisme.
//   - /sign-in        (page de connexion)
//   - /deconnexion    (la sortie du menu commun — une session déjà expirée doit
//                      pouvoir la traverser vers Keycloak, pas prendre un 307)
//   - /_next/*        (assets compilés)
//   - /favicon.ico
//   - /dsfr/*         (assets DSFR statiques éventuels)
export const config = {
  matcher: [
    '/((?!api/auth|api/health|api/ab|sign-in|deconnexion|_next/static|_next/image|favicon.ico|favicon.svg|dsfr).*)',
  ],
};
