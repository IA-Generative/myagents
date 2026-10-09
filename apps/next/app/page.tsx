// Page d'accueil — redirige vers /agents si l'utilisateur est authentifié,
// sinon vers la page de connexion.

import { redirect } from 'next/navigation';
import { getServerSession } from 'next-auth';
import { authOptions } from '@/lib/auth';

export default async function HomePage() {
  const session = await getServerSession(authOptions);
  redirect(session ? '/agents' : '/sign-in');
}
