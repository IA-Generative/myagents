// Étape 4 — Test et publication (§3.1).
// Les 3 boutons de publication persistent l'agent en base via POST /api/ab/agents
// (stockage Prisma, pas encore d'intégration OpenWebUI). Sur succès, redirect
// vers /agents avec un paramètre d'état affiché en bannière.

'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { useWizard } from '../_context';

type PublishStatus = 'draft' | 'published' | 'submitted';

export function StepTestPublish() {
  const router = useRouter();
  const { draft } = useWizard();
  const [busy, setBusy] = useState<null | PublishStatus>(null);
  const [error, setError] = useState<string | null>(null);

  const isValid = draft.name.trim().length > 0 && draft.systemPrompt.trim().length > 0;

  async function save(status: PublishStatus) {
    if (!isValid) {
      setError("Le nom et les instructions système sont obligatoires (étapes 1 et 2).");
      return;
    }
    setBusy(status);
    setError(null);
    try {
      const res = await fetch('/api/ab/agents', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ...draft, status }),
      });
      if (!res.ok) {
        const detail = await res.json().catch(() => ({}));
        setError(detail.message ?? `Erreur ${res.status} : ${detail.error ?? 'inconnue'}`);
        setBusy(null);
        return;
      }
      router.push(`/agents?saved=${status}`);
    } catch (err) {
      setError(String(err));
      setBusy(null);
    }
  }

  return (
    <div className="fr-grid-row fr-grid-row--gutters">
      {/* Récapitulatif */}
      <div className="fr-col-12">
        <div className="fr-callout">
          <h3 className="fr-callout__title">Récapitulatif de votre agent</h3>
          <dl className="fr-mb-0">
            <dt>
              <strong>Nom :</strong>
            </dt>
            <dd>{draft.name || <em>(non renseigné)</em>}</dd>
            <dt className="fr-mt-1w">
              <strong>Description :</strong>
            </dt>
            <dd>{draft.description || <em>(non renseigné)</em>}</dd>
            <dt className="fr-mt-1w">
              <strong>Visibilité :</strong>
            </dt>
            <dd>
              {draft.visibility === 'private' && 'Privé'}
              {draft.visibility === 'community' &&
                `Communauté ${draft.communityPath ?? '(non choisie)'}`}
              {draft.visibility === 'ministry' && 'Tout le ministère'}
            </dd>
            <dt className="fr-mt-1w">
              <strong>Modèle :</strong>
            </dt>
            <dd>{draft.modelId}</dd>
            <dt className="fr-mt-1w">
              <strong>Prompt système :</strong>
            </dt>
            <dd>
              {draft.systemPrompt ? (
                `${draft.systemPrompt.slice(0, 200)}${draft.systemPrompt.length > 200 ? '…' : ''}`
              ) : (
                <em>(non renseigné)</em>
              )}
            </dd>
          </dl>
        </div>
      </div>

      <div className="fr-col-12 fr-col-md-6">
        <h3>
          Prévisualisation{' '}
          <span className="fr-badge fr-badge--warning fr-badge--sm">En construction</span>
        </h3>
        {/* Texte destiné à l'utilisateur : on parle de « Mon assistant », jamais
            du nom technique du socle. Un brouillon n'est pas poussé dans Mon
            assistant (cf. POST /api/ab/agents) : seul un agent publié s'y teste. */}
        <div className="fr-callout">
          <p className="fr-callout__text">
            La conversation de test avec l&apos;agent, directement sur cette page, n&apos;est
            pas encore disponible. Pour l&apos;instant, publiez l&apos;agent puis testez-le dans
            Mon assistant, ou utilisez « Utiliser rapidement ici » depuis la liste de vos
            agents (fonctionne aussi pour un brouillon).
          </p>
        </div>
      </div>

      <div className="fr-col-12 fr-col-md-6">
        <h3>Publication</h3>
        <div className="fr-btns-group">
          <button
            type="button"
            className="fr-btn fr-btn--secondary"
            disabled={busy !== null || !isValid}
            onClick={() => save('draft')}
          >
            {busy === 'draft' ? 'Sauvegarde…' : 'Sauvegarder en brouillon'}
          </button>
          <button
            type="button"
            className="fr-btn"
            disabled={busy !== null || !isValid}
            onClick={() => save('published')}
          >
            {busy === 'published' ? 'Publication…' : 'Publier dans mon espace'}
          </button>
          <button
            type="button"
            className="fr-btn fr-btn--tertiary"
            disabled={busy !== null || !isValid || draft.visibility !== 'ministry'}
            onClick={() => save('submitted')}
            title={
              draft.visibility !== 'ministry'
                ? 'Disponible uniquement si la visibilité est « Tout le ministère »'
                : undefined
            }
          >
            {busy === 'submitted' ? 'Soumission…' : 'Proposer au catalogue'}
          </button>
        </div>
        {!isValid && (
          <p className="fr-text--sm fr-mt-2w" style={{ color: 'var(--text-mention-grey)' }}>
            Remplissez au moins le <strong>nom</strong> (étape 1) et les{' '}
            <strong>instructions système</strong> (étape 2) pour pouvoir publier.
          </p>
        )}
        {error && (
          <div className="fr-alert fr-alert--error fr-alert--sm fr-mt-2w">
            <p>{error}</p>
          </div>
        )}
      </div>
    </div>
  );
}
