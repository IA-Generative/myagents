// Configuration NextAuth — mode standalone (sans Keycloak/OpenWebUI).
// Provider "Credentials" auto-authentifiant un unique utilisateur de dev
// local ; à remplacer par un vrai provider si une auth réelle est requise.

import type { NextAuthOptions } from 'next-auth';
import CredentialsProvider from 'next-auth/providers/credentials';

// UUID fixe utilisé comme creator_id / user_id côté Prisma (colonnes @db.Uuid).
export const DEV_USER_ID = '00000000-0000-0000-0000-000000000001';

export const authOptions: NextAuthOptions = {
  providers: [
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
    async jwt({ token, user }) {
      if (user) {
        token.sub = user.id;
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
