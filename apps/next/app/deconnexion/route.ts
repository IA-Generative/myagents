// La sortie que le menu commun de la bêta sait appeler d'un simple lien
// (`sortie: '/deconnexion'` dans la table APPS de mirai-apps-menu).
//
// Trois différences avec le signOut() NextAuth qu'elle remplace :
// · le NAVIGATEUR traverse le end_session Keycloak — les cookies du SSO tombent
//   aussi, là où le fetch serveur de events.signOut les laissait intacts ;
// · un échec devient VISIBLE (page d'erreur Keycloak) au lieu d'un console.warn
//   que personne ne lit ;
// · les cookies NextAuth sont supprimés Y COMPRIS leurs fragments .0/.1/… — le
//   JWT porte les jetons Keycloak et se découpe au-delà de ~4 Ko (c'est la
//   raison d'être du proxy-buffer-size 16k de l'Ingress). N'effacer que le nom
//   de base laisserait la session vivante : une déconnexion qui n'en est pas une.

import { getToken } from 'next-auth/jwt';
import { NextResponse } from 'next/server';
import type { NextRequest } from 'next/server';
import { env } from '@/lib/env';

export async function GET(req: NextRequest) {
  const e = env();
  const token = await getToken({ req, secret: e.NEXTAUTH_SECRET });

  const base = e.KEYCLOAK_ISSUER.replace(/\/$/, '');
  const sortie = new URL(`${base}/protocol/openid-connect/logout`);
  sortie.searchParams.set(
    'post_logout_redirect_uri',
    `${e.NEXTAUTH_URL.replace(/\/$/, '')}/sign-in`
  );
  if (token?.idToken) {
    // Avec le hint, Keycloak ferme sans écran de confirmation.
    sortie.searchParams.set('id_token_hint', String(token.idToken));
  } else {
    // Session locale déjà morte : on passe quand même par Keycloak — idempotent,
    // et c'est lui qui sait s'il reste une session SSO à fermer.
    sortie.searchParams.set('client_id', e.KEYCLOAK_CLIENT_ID);
  }

  const reponse = NextResponse.redirect(sortie, { status: 302 });

  // ⚠ Un cookie préfixé __Secure-/__Host- ne peut être SUPPRIMÉ que par un
  //   Set-Cookie portant lui-même `Secure` (le navigateur rejette le reste en
  //   silence) : on pose les attributs explicitement, on ne fait pas confiance
  //   aux défauts de delete(). Supprimer un cookie absent est sans effet.
  const efface = (nom: string, secure: boolean) => {
    reponse.cookies.set(nom, '', {
      path: '/',
      maxAge: 0,
      httpOnly: true,
      sameSite: 'lax',
      secure,
    });
  };
  for (const [nom, secure] of [
    ['next-auth.session-token', false],
    ['__Secure-next-auth.session-token', true],
  ] as const) {
    efface(nom, secure);
    for (let i = 0; i < 6; i += 1) efface(`${nom}.${i}`, secure);
  }
  efface('next-auth.callback-url', false);
  efface('__Secure-next-auth.callback-url', true);
  efface('next-auth.csrf-token', false);
  efface('__Host-next-auth.csrf-token', true);

  return reponse;
}
