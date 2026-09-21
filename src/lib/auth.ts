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
