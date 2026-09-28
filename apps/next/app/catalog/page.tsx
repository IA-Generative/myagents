// Catalogue communautaire — stub. Implémentation prévue pour la V1 (PI-8).
// Protection SSO assurée globalement par middleware.ts.

import Link from 'next/link';

export default function CatalogPage() {
  return (
    <div>
      <h1>Catalogue des agents</h1>
      <p className="fr-text--lead">
        Le catalogue communautaire vous permettra de découvrir et réutiliser les agents
        créés par les autres directions du ministère.
      </p>

      <div className="fr-callout fr-icon-time-line fr-mb-4w">
        <h2 className="fr-callout__title">Bientôt disponible</h2>
        <p className="fr-callout__text">
          Le catalogue communautaire sera disponible en V1 (PI-8). Vous pourrez y
          rechercher, filtrer, noter et forker les agents partagés par les autres
          directions.
        </p>
      </div>

      <h2 className="fr-h3">En attendant, que souhaitez-vous faire&nbsp;?</h2>
      <div className="fr-grid-row fr-grid-row--gutters">
        <div className="fr-col-12 fr-col-md-6">
          <div className="fr-tile fr-enlarge-link">
            <div className="fr-tile__body">
              <div className="fr-tile__content">
                <h3 className="fr-tile__title">
                  <Link href="/agents/new" className="fr-tile__link">
                    Créer votre propre agent
                  </Link>
                </h3>
                <p className="fr-tile__desc">
                  Lancez l&apos;assistant guidé pour créer un agent personnalisé en
                  moins de 5 minutes.
                </p>
              </div>
            </div>
          </div>
        </div>
        <div className="fr-col-12 fr-col-md-6">
          <div className="fr-tile fr-enlarge-link">
            <div className="fr-tile__body">
              <div className="fr-tile__content">
                <h3 className="fr-tile__title">
                  <Link href="/agents" className="fr-tile__link">
                    Voir mes agents
                  </Link>
                </h3>
                <p className="fr-tile__desc">
                  Retrouvez les agents que vous avez créés, leurs statistiques et leurs
                  versions.
                </p>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
