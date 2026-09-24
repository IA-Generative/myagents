// Augmentation des types next-auth.
// Session : expose uniquement user.id cote client (cf. src/lib/auth.ts).

import 'next-auth';

declare module 'next-auth' {
  interface Session {
    user: {
      id: string;
      name?: string | null;
      email?: string | null;
      image?: string | null;
    };
  }
}
