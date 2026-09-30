// Configuration NextAuth — provider Keycloak (realm `myagents`).
// Fallback Credentials en mode standalone (sans SSO) pour les tests E2E.

import type { NextAuthOptions } from 'next-auth';
import KeycloakProvider from 'next-auth/providers/keycloak';
import CredentialsProvider from 'next-auth/providers/credentials';

import { env } from '@/lib/env';

// UUID fixe utilisé comme creator_id / user_id côté Prisma (colonnes @db.Uuid).
export const DEV_USER_ID = '00000000-0000-0000-0000-000000000001';

export const authOptions: NextAuthOptions = {
  providers: [
    KeycloakProvider({
      clientId: env().KEYCLOAK_CLIENT_ID,
      clientSecret: env().KEYCLOAK_CLIENT_SECRET,
      issuer: env().KEYCLOAK_ISSUER,
      authorization: {
        params: { scope: 'openid profile email roles' },
      },
    }),
    CredentialsProvider({
      name: 'dev',
      credentials: {},
      async authorize() {
        return { id: DEV_USER_ID, name: 'Utilisateur local', email: 'dev@localhost' };
      },
    }),
  ],
  session: {
    strategy: 'jwt',
    // 12 h et non le défaut de TRENTE JOURS : une session applicative ne doit pas
    // survivre des semaines à la session SSO qui l'a ouverte (lot 9, incrément 3 —
    // le realm ne se touche pas, l'alignement se fait côté applications).
    maxAge: 12 * 60 * 60,
  },
  callbacks: {
    // Restriction d'acces au groupe declare dans OIDC_GROUPE_EXIGE. Le claim
    // `groups` porte le NOM FEUILLE des groupes (mapper Keycloak full.path=false),
    // jamais leur chemin : on compare donc a un nom, pas a un « /chemin/groupe ».
    // Variable absente = aucune restriction, comportement historique inchange.
    async signIn({ profile }) {
      const exige = env().OIDC_GROUPE_EXIGE;
      if (!exige) return true;
      const brut = (profile as { groups?: unknown } | undefined)?.groups;
      const groupes = Array.isArray(brut)
        ? brut.map(String)
        : typeof brut === 'string'
          ? [brut]
          : [];
      if (groupes.includes(exige)) return true;
      // Tracer le refus sans nommer la personne : le motif suffit au diagnostic.
      console.warn(
        `Acces refuse : le jeton ne porte pas le groupe requis (${groupes.length} groupe(s) presente(s))`,
      );
      return false;
    },
    async jwt({ token, account }) {
      // Premier appel après login : on récupère l'access token Keycloak.
      // `token.sub` est automatiquement posé par next-auth à partir du
      // claim "sub" de l'ID token — c'est l'UUID Keycloak de l'utilisateur,
      // qu'on utilise ensuite comme creator_id côté Prisma.
      if (account) {
        token.accessToken = account.access_token;
        token.refreshToken = account.refresh_token;
        token.expiresAt = account.expires_at;
        // Conservé pour la déconnexion fédérée Keycloak (id_token_hint).
        token.idToken = account.id_token;
      }
      return token;
    },
    async session({ session, token }) {
      if (session.user && token.sub) {
        session.user.id = token.sub;
      }
      return session;
    },
  },
  pages: {
    signIn: '/sign-in',
  },
};
