// Page de connexion — SSO Keycloak ; connexion locale seulement si AUTH_LOCALE=true hors
// production (voir src/lib/auth.ts).

'use client';

import { signIn } from 'next-auth/react';

const AUTH_LOCALE = process.env.NEXT_PUBLIC_AUTH_LOCALE === 'true';

export default function SignInPage() {
  return (
    <div className="fr-grid-row fr-grid-row--center">
      <div className="fr-col-12 fr-col-md-8 fr-col-lg-6">
        <h1>Bienvenue sur Mes Agents MirAI</h1>
        <p className="fr-text--lead">
          Créez vos propres agents IA souverains en quelques minutes, sans écrire de code.
        </p>

        <div className="fr-callout fr-mb-4w">
          <h2 className="fr-callout__title">Que souhaitez-vous faire&nbsp;?</h2>
          <p className="fr-callout__text">
            Pour rédiger un assistant IA adapté à votre métier (rédaction de notes,
            analyse juridique, accueil usager, synthèse de réunion…), continuez
            ci-dessous.
          </p>
          <button
            className="fr-btn fr-btn--lg fr-btn--icon-left fr-icon-account-circle-line"
            onClick={() => signIn('keycloak', { callbackUrl: '/agents' })}
          >
            Se connecter avec Keycloak
          </button>
          {AUTH_LOCALE && (
            <button
              className="fr-btn fr-btn--secondary fr-btn--lg fr-ml-2w"
              onClick={() => signIn('credentials', { callbackUrl: '/agents' })}
            >
              Continuer sans SSO (local)
            </button>
          )}
        </div>

        <h2 className="fr-h5">À quoi sert Mes Agents MirAI&nbsp;?</h2>
        <ul>
          <li>Créer un agent IA spécialisé en moins de 5 minutes, guidé pas à pas</li>
          <li>Tester votre agent en direct avant de le publier</li>
          <li>Partager vos agents avec votre service ou tout le ministère</li>
          <li>Découvrir les agents publiés par les autres directions</li>
        </ul>

        <p className="fr-text--sm" style={{ color: 'var(--text-mention-grey)' }}>
          Hébergé sur Cloud Pi Native · Modèles IA souverains servis par Scaleway ·
          Conforme DSFR et RGAA 4.1
        </p>
      </div>
    </div>
  );
}
