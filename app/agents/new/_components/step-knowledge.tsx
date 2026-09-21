// Étape 3 — Connaissances et outils (§3.1). Stub : les champs visibles
// correspondent aux fonctionnalités décrites mais ne sont pas câblés. Chaque
// bloc porte son état (badge) pour qu'on ne les prenne pas pour une panne.

export function StepKnowledge() {
  return (
    <div className="fr-grid-row fr-grid-row--gutters">
      <div className="fr-col-12">
        <div className="fr-upload-group">
          <label className="fr-label" htmlFor="knowledge-upload">
            Collection documentaire{' '}
            <span className="fr-badge fr-badge--warning fr-badge--sm">En construction</span>
            <span className="fr-hint-text">PDF, DOCX, TXT, CSV, XLSX</span>
          </label>
          <input className="fr-upload" type="file" id="knowledge-upload" multiple disabled />
        </div>
        {/* Le dépôt de documents n'est pas encore branché : on indique le
            chemin qui fonctionne aujourd'hui (Mes collections). */}
        <p className="fr-text--sm fr-mt-1w fr-mb-0">
          <span className="fr-icon-information-line fr-icon--sm" aria-hidden="true" />{' '}
          En attendant : créez votre base documentaire dans{' '}
          <a
            href="https://mescollections.numerique-interieur.com/"
            target="_blank"
            rel="noopener noreferrer"
            title="Mes collections — nouvelle fenêtre"
          >
            Mes collections
          </a>{' '}
          — elle apparaît ensuite comme modèle dans Mon assistant.
        </p>
      </div>
      <div className="fr-col-12">
        <fieldset className="fr-fieldset">
          <legend className="fr-fieldset__legend">Outils MirAI (aucun connecté pour l&apos;instant)</legend>
          <div className="fr-fieldset__content">
            <div className="fr-checkbox-group">
              <input type="checkbox" id="tool-web" disabled />
              <label className="fr-label" htmlFor="tool-web">Recherche web</label>
            </div>
            <div className="fr-checkbox-group">
              <input type="checkbox" id="tool-image" disabled />
              <label className="fr-label" htmlFor="tool-image">Génération d&apos;image</label>
            </div>
          </div>
        </fieldset>
      </div>
      <div className="fr-col-12">
        <div className="fr-notice fr-notice--info">
          <div className="fr-container">
            <div className="fr-notice__body">
              <p className="fr-notice__title">
                Connecteurs SI, index mail et chaînage inter-agents : bientôt disponibles.
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
