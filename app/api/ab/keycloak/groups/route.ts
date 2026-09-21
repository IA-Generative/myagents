// BFF — retourne les groupes de l'utilisateur connecté.
//
// Mode standalone (pas de Keycloak) : il n'y a pas de source de groupes,
// on renvoie donc toujours une liste vide. Le sélecteur de groupe "community"
// dans le wizard affichera simplement qu'aucun groupe n'est disponible.

import { NextResponse } from 'next/server';
import type { NextRequest } from 'next/server';
import { getToken } from 'next-auth/jwt';
import { env } from '@/lib/env';

export async function GET(req: NextRequest) {
  const token = await getToken({ req, secret: env().NEXTAUTH_SECRET });
  if (!token) {
    return NextResponse.json({ error: 'unauthorized' }, { status: 401 });
  }

  return NextResponse.json({
    groups: [],
    hint: 'Aucun fournisseur de groupes configuré en mode standalone.',
  });
}
