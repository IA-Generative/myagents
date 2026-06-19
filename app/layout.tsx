// Layout racine — habille toute l'application avec le DSFR.
// Header / footer ministériels, typographie Marianne, lang="fr".

import type { Metadata } from 'next';
import type { ReactNode } from 'react';
import Link from 'next/link';
import { getServerSession } from 'next-auth';
import { authOptions } from '@/lib/auth';
import { HeaderAccount } from './_components/header-account';
import './globals.css';

export const metadata: Metadata = {
  title: 'Mes Agents MirAI (beta)',
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
                    <Link href="/" title="Accueil — Mes Agents MirAI">
                      <p className="fr-header__service-title">
                        Mes Agents MirAI{' '}
                        <span className="fr-badge fr-badge--sm fr-badge--green-emeraude">Beta</span>
                      </p>
                    </Link>
                    <p className="fr-header__service-tagline">
                      Créez vos agents IA souverains
                    </p>
                  </div>
                </div>
                {displayName && (
                  <div className="fr-header__tools">
                    <div className="fr-header__tools-links">
                      <HeaderAccount displayName={displayName} />
                    </div>
                  </div>
                )}
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
      </body>
    </html>
  );
}
