// Layout racine — habille toute l'application avec le DSFR.
// Header / footer ministériels, typographie Marianne, lang="fr".

import type { Metadata } from 'next';
import type { ReactNode } from 'react';
import Link from 'next/link';
import { getServerSession } from 'next-auth';
import { authOptions } from '@/lib/auth';
import './globals.css';

export const metadata: Metadata = {
  // Casse de phrase, sans mention bêta : la pastille « MirAI Next Beta » du menu
  // commun porte déjà ce repère (docs/nommage.md du dépôt mirai-apps-menu).
  title: 'Mes agents',
  description:
    "Créer, partager et utiliser des agents IA souverains pour les agents du Ministère de l'Intérieur",
  icons: {
    icon: [{ url: '/favicon.svg', type: 'image/svg+xml' }],
  },
};

export default async function RootLayout({ children }: { children: ReactNode }) {
  const session = await getServerSession(authOptions);
  const displayName = session?.user
    ? session.user.name || session.user.email || 'agent'
    : null;

  return (
    <html lang="fr" data-fr-scheme="system">
      <head>
        {/* DSFR servi comme asset statique depuis public/dsfr/ (voir Dockerfile).
            On évite @import dans globals.css qui fait exploser webpack sur
            l'arborescence d'imports de react-dsfr/main.css. */}
        <link rel="stylesheet" href="/dsfr/dsfr.min.css" />
        <link rel="stylesheet" href="/dsfr/utility/icons/icons.min.css" />
        <link rel="stylesheet" href="/dsfr/utility/utility.min.css" />
      </head>
      <body>
        <header className="fr-header" role="banner">
          <div className="fr-header__body">
            <div className="fr-container">
              <div className="fr-header__body-row">
                <div className="fr-header__brand fr-enlarge-link">
                  <div className="fr-header__brand-top">
                    <div className="fr-header__logo">
                      <p className="fr-logo">
                        République
                        <br />
                        Française
                      </p>
                    </div>
                    <div className="fr-header__operator">
                      {/* eslint-disable-next-line @next/next/no-img-element */}
                      <img
                        src="/favicon.svg"
                        alt="Mes Agents MirAI"
                        width={40}
                        height={40}
                        style={{ maxHeight: '40px', width: 'auto' }}
                      />
                    </div>
                  </div>
                  <div className="fr-header__service">
                    <Link href="/" title="Accueil — Mes agents">
                      <p className="fr-header__service-title">
                        Mes agents{' '}

                      </p>
                    </Link>
                    <p className="fr-header__service-tagline">
                      Créez vos agents IA souverains
                    </p>
                  </div>
                </div>
                {/* Le nom et « Se déconnecter » sont portés par le menu commun de la
                    bêta (bulle en haut à droite, sortie GET /deconnexion) : une seule
                    commande de compte à l'écran. */}
              </div>
            </div>
          </div>
        </header>
        <main role="main" id="contenu" className="fr-container fr-py-6w">
          {children}
        </main>
        <footer className="fr-footer" role="contentinfo">
          <div className="fr-container">
            <div className="fr-footer__body">
              <div className="fr-footer__brand fr-enlarge-link">
                <Link href="/" title="Accueil — Mes Agents MirAI">
                  <p className="fr-logo">
                    République
                    <br />
                    Française
                  </p>
                </Link>
              </div>
              <div className="fr-footer__content">
                <p className="fr-footer__content-desc">
                  Mes Agents MirAI — hébergé sur Cloud Pi Native, conforme DSFR et RGAA 4.1.
                </p>
              </div>
            </div>
            <div className="fr-footer__bottom">
              <ul className="fr-footer__bottom-list">
                <li className="fr-footer__bottom-item">
                  <a className="fr-footer__bottom-link" href="#">
                    Accessibilité : partiellement conforme
                  </a>
                </li>
                <li className="fr-footer__bottom-item">
                  <a className="fr-footer__bottom-link" href="#">
                    Mentions légales
                  </a>
                </li>
              </ul>
            </div>
          </div>
        </footer>
        {/* Le menu commun de la bêta — servi en même origine par l'Ingress `/_beta`,
            depuis `IA-Generative/mirai-apps-menu`. L'identité alimente la bulle du
            compte ; `<` échappé pour qu'aucun nom ne puisse fermer le script. */}
        {displayName && (
          <script
            dangerouslySetInnerHTML={{
              __html: `window.MIRAI_MENU={nom:${JSON.stringify(displayName).replace(/</g, '\\u003c')},mail:${JSON.stringify(session?.user?.email || '').replace(/</g, '\\u003c')}};`,
            }}
          />
        )}
        <script src="/_beta/menu.js" async></script>
      </body>
    </html>
  );
}
