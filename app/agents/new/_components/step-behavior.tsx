// Étape 2 — Comportement (§3.1).
// Lit / écrit via useWizard() depuis _context.tsx.

'use client';

import { useState, useEffect, useCallback } from 'react';
import {
  AVAILABLE_MODELS,
  TIER_LABELS,
  TIER_COLORS,
  getModelById,
  type ModelProfile,
} from '@/lib/models';
import { useWizard } from '../_context';

export function StepBehavior() {
  const { draft, update, promptValidated, setPromptValidated } = useWizard();
  const [busy, setBusy] = useState<null | 'assist' | 'optimize' | 'starters' | 'validate'>(null);
  const [error, setError] = useState<string | null>(null);

  // Liste des modèles chargée dynamiquement depuis /api/ab/models (cache serveur).
  // On part du catalogue statique pour un affichage immédiat, puis on remplace
  // par la liste live en tâche de fond.
  const [models, setModels] = useState<ModelProfile[]>(AVAILABLE_MODELS);
  const [modelsLoading, setModelsLoading] = useState(false);
  const [modelsSource, setModelsSource] = useState<string | null>(null);

  const loadModels = useCallback(async (refresh = false) => {
    setModelsLoading(true);
    try {
      const res = await fetch(`/api/ab/models${refresh ? '?refresh=1' : ''}`);
      if (res.ok) {
        const data = (await res.json()) as { models?: ModelProfile[]; source?: string };
        if (Array.isArray(data.models) && data.models.length > 0) {
          setModels(data.models);
          setModelsSource(data.source ?? null);
        }
      }
    } catch {
      // on garde le catalogue statique déjà affiché
    } finally {
      setModelsLoading(false);
    }
  }, []);

  useEffect(() => {
    loadModels(false);
  }, [loadModels]);

  // Le modèle sélectionné peut venir de la liste live ou (à défaut) du catalogue.
  const selectedModel =
    models.find((m) => m.id === draft.modelId) ?? getModelById(draft.modelId);
  // Garantit que la valeur courante figure toujours comme option du select.
  const options =
    selectedModel && !models.some((m) => m.id === draft.modelId)
      ? [selectedModel, ...models]
      : models;

  async function callPromptBff(path: string, kind: 'assist' | 'optimize') {
    setBusy(kind);
    setError(null);
    try {
      const res = await fetch(path, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ prompt: draft.systemPrompt, hints: {} }),
      });
      if (!res.ok) {
        const detail = await res.json().catch(() => ({}));
        setError(detail.message ?? `Erreur ${res.status} : ${detail.error ?? 'inconnue'}`);
        return;
      }
      const data = await res.json();
      if (typeof data.prompt === 'string') update({ systemPrompt: data.prompt });
    } catch (err) {
      setError(String(err));
    } finally {
      setBusy(null);
    }
  }

  async function generateStarters() {
    if (!draft.systemPrompt || draft.systemPrompt.trim().length < 20) {
      setError('Le prompt système doit faire au moins 20 caractères pour générer une amorce.');
      return;
    }
    setBusy('starters');
    setError(null);
    try {
      const res = await fetch('/api/ab/prompt/suggest-starters', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ prompt: draft.systemPrompt, count: 4 }),
      });
      if (!res.ok) {
        const detail = await res.json().catch(() => ({}));
        setError(detail.message ?? `Erreur ${res.status} : ${detail.error ?? 'inconnue'}`);
        return;
      }
      const data = (await res.json()) as { greeting?: string; examples?: string[] };
      const patch: Partial<{ greeting: string; examples: string[] }> = {};
      if (typeof data.greeting === 'string') patch.greeting = data.greeting;
      if (Array.isArray(data.examples)) patch.examples = data.examples;
      update(patch);
    } catch (err) {
      setError(String(err));
    } finally {
      setBusy(null);
    }
  }

  // Validation OBLIGATOIRE des instructions système par le module anti-jailbreak.
  // Tant que ce n'est pas validé, la navigation « Suivant » est bloquée (cf. page.tsx).
  async function validateSystemPrompt() {
    if (!draft.systemPrompt || draft.systemPrompt.trim().length === 0) {
      setError('Saisissez des instructions système avant de les valider.');
      return;
    }
    setBusy('validate');
    setError(null);
    try {
      const res = await fetch('/api/ab/prompt/validate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ prompt: draft.systemPrompt }),
      });
      if (!res.ok) {
        const detail = await res.json().catch(() => ({}));
        setPromptValidated(false);
        setError(detail.message ?? `Erreur ${res.status} : ${detail.error ?? 'inconnue'}`);
        return;
      }
      setPromptValidated(true);
    } catch (err) {
      setPromptValidated(false);
      setError(String(err));
    } finally {
      setBusy(null);
    }
  }

  function updateExample(index: number, value: string) {
    update({
      examples: draft.examples.map((e, i) => (i === index ? value : e)),
    });
  }

  function addExample() {
    if (draft.examples.length >= 6) return;
    update({ examples: [...draft.examples, ''] });
  }

  function removeExample(index: number) {
    update({ examples: draft.examples.filter((_, i) => i !== index) });
  }

  return (
    <div className="fr-grid-row fr-grid-row--gutters">
      {/* ---- System prompt + assist / optimize ---- */}
      <div className="fr-col-12">
        <div className="fr-input-group">
          <label className="fr-label" htmlFor="system-prompt">
            Instructions système
            <span className="fr-hint-text">
              Décris le rôle, le public, le ton et les contraintes de l&apos;agent.
              Si tu hésites, clique sur « Aide-moi à écrire ». 10 000 caractères max.
            </span>
          </label>
          <textarea
            className="fr-input"
            id="system-prompt"
            rows={10}
            maxLength={10000}
            value={draft.systemPrompt}
            onChange={(e) => update({ systemPrompt: e.target.value })}
            placeholder={`Ex :

Tu es un assistant spécialisé dans la rédaction de notes juridiques pour les agents
de la DLPAJ. Ton rôle est d'aider à produire des notes claires, structurées et
juridiquement rigoureuses à partir d'une question posée par l'utilisateur.

Public : agents de la Direction des libertés publiques et des affaires juridiques.
Ton : formel, précis, sans jargon excessif.

Contraintes :
- Cite systématiquement les articles de loi et textes réglementaires applicables
- Ne jamais inventer de références juridiques
- Structure tes notes en 3 parties : rappel du cadre légal, analyse, préconisation
- Si la question dépasse ton périmètre, indique-le clairement
- Réponds toujours en français administratif`}
          />
        </div>
        <div className="fr-btns-group fr-btns-group--inline">
          <button
            type="button"
            className="fr-btn fr-btn--secondary"
            disabled={busy !== null}
            onClick={() => callPromptBff('/api/ab/prompt/assist', 'assist')}
          >
            {busy === 'assist' ? 'Génération…' : 'Aide-moi à écrire'}
          </button>
          <button
            type="button"
            className="fr-btn fr-btn--secondary"
            disabled={busy !== null || !draft.systemPrompt}
            onClick={() => callPromptBff('/api/ab/prompt/optimize', 'optimize')}
          >
            {busy === 'optimize' ? 'Optimisation…' : 'Optimiser mon prompt'}
          </button>
        </div>

        {/* ---- Validation obligatoire des instructions système ---- */}
        <div className="fr-mt-2w" style={{ display: 'flex', alignItems: 'center', gap: '1rem', flexWrap: 'wrap' }}>
          <button
            type="button"
            className={
              promptValidated
                ? 'fr-btn fr-btn--icon-left fr-icon-checkbox-circle-line'
                : 'fr-btn fr-btn--secondary fr-btn--icon-left fr-icon-shield-line'
            }
            disabled={busy !== null || !draft.systemPrompt || promptValidated}
            onClick={validateSystemPrompt}
            aria-live="polite"
          >
            {busy === 'validate'
              ? 'Validation…'
              : promptValidated
                ? 'Instructions validées ✓'
                : 'Valider les instructions système'}
          </button>
          <span className="fr-hint-text" style={{ margin: 0 }}>
            {promptValidated
              ? 'Vous pouvez passer à l’étape suivante.'
              : 'La validation des instructions système est obligatoire avant de passer à l’étape suivante.'}
          </span>
        </div>

        {error && (
          <div className="fr-alert fr-alert--error fr-alert--sm fr-mt-2w">
            <p>{error}</p>
            <p className="fr-text--sm fr-mb-0">Modifiez vos instructions système, puis validez à nouveau.</p>
          </div>
        )}
      </div>

      {/* ---- Amorce + exemples générés ---- */}
      <div className="fr-col-12">
        <div className="fr-input-group">
          <label className="fr-label" htmlFor="greeting">
            Amorce de conversation
            <span className="fr-hint-text">
              Message d&apos;accueil affiché à l&apos;utilisateur au lancement de l&apos;agent.
            </span>
          </label>
          <textarea
            className="fr-input"
            id="greeting"
            rows={3}
            maxLength={500}
            value={draft.greeting}
            onChange={(e) => update({ greeting: e.target.value })}
            placeholder="Ex : Bonjour, je suis votre assistant de rédaction juridique. Posez-moi une question sur le CESEDA et je vous aiderai à préparer une note structurée, sourcée sur les textes en vigueur."
          />
        </div>
        <button
          type="button"
          className="fr-btn fr-btn--secondary fr-btn--icon-left fr-icon-magic-wand-line"
          disabled={busy !== null || draft.systemPrompt.trim().length < 20}
          onClick={generateStarters}
        >
          {busy === 'starters' ? 'Génération…' : 'Générer amorce + exemples depuis le prompt'}
        </button>
      </div>

      <div className="fr-col-12">
        <fieldset className="fr-fieldset">
          <legend className="fr-fieldset__legend">
            <span className="fr-fieldset__legend--regular">Exemples de prompts (cliquables)</span>
            <span className="fr-hint-text">
              Jusqu&apos;à 6 suggestions proposées à l&apos;utilisateur final. Peut être
              généré depuis le prompt système avec le bouton ci-dessus, ou saisi à la main.
            </span>
          </legend>
          <div className="fr-fieldset__content">
            {draft.examples.length === 0 && (
              <p className="fr-text--sm" style={{ color: 'var(--text-mention-grey)' }}>
                Aucun exemple pour l&apos;instant.
              </p>
            )}
            {draft.examples.map((example, i) => (
              <div
                key={i}
                className="fr-mb-2w"
                style={{ display: 'flex', gap: '0.5rem', alignItems: 'flex-start' }}
              >
                <input
                  type="text"
                  className="fr-input"
                  value={example}
                  maxLength={200}
                  onChange={(e) => updateExample(i, e.target.value)}
                  placeholder={
                    [
                      'Ex : Comment contester un refus de visa ?',
                      'Ex : Quels sont les délais pour un recours gracieux ?',
                      'Ex : Peut-on refuser un titre de séjour pour ordre public ?',
                      'Ex : Rédige-moi une note sur le droit d\'asile.',
                      'Ex : Synthétise ce dossier en 5 points clés.',
                      'Ex : Compare ces deux articles du CESEDA.',
                    ][i] ?? "Ex : ma question pour l'agent…"
                  }
                  style={{ flex: 1 }}
                />
                <button
                  type="button"
                  className="fr-btn fr-btn--tertiary fr-btn--sm fr-icon-delete-line"
                  title="Retirer cet exemple"
                  onClick={() => removeExample(i)}
                >
                  Retirer
                </button>
              </div>
            ))}
            {draft.examples.length < 6 && (
              <button
                type="button"
                className="fr-btn fr-btn--tertiary-no-outline fr-btn--icon-left fr-icon-add-line"
                onClick={addExample}
              >
                Ajouter un exemple
              </button>
            )}
          </div>
        </fieldset>
      </div>

      {/* ---- Sélecteur de modèle de base (menu déroulant + détails) ---- */}
      <div className="fr-col-12">
        <div style={{ display: 'flex', alignItems: 'flex-end', gap: '1rem', flexWrap: 'wrap' }}>
          <div className="fr-select-group" style={{ flex: 1, minWidth: '260px', marginBottom: 0 }}>
            <label className="fr-label" htmlFor="model-select">
              Modèle de base
              <span className="fr-hint-text">
                Choisissez le moteur IA. Les détails du modèle s&apos;affichent ci-dessous.
              </span>
            </label>
            <select
              className="fr-select"
              id="model-select"
              value={draft.modelId}
              onChange={(e) => update({ modelId: e.target.value })}
            >
              {options.map((m) => (
                <option key={m.id} value={m.id}>
                  {m.label} — {TIER_LABELS[m.tier]} · {m.family}
                </option>
              ))}
            </select>
          </div>
          <button
            type="button"
            className="fr-btn fr-btn--secondary fr-btn--icon-left fr-icon-refresh-line"
            onClick={() => loadModels(true)}
            disabled={modelsLoading}
            title="Recharger la liste des modèles disponibles"
          >
            {modelsLoading ? 'Actualisation…' : 'Actualiser'}
          </button>
        </div>
        <p className="fr-text--xs fr-mt-1w" style={{ color: 'var(--text-mention-grey)' }}>
          {modelsLoading
            ? 'Chargement de la liste des modèles disponibles…'
            : modelsSource === 'live' || modelsSource === 'cache' || modelsSource === 'stale'
              ? `${models.length} modèles disponibles sur l'instance souveraine.`
              : 'Liste de secours (catalogue local) — instance momentanément injoignable.'}
        </p>
      </div>

      {/* ---- Détails du modèle sélectionné ---- */}
      {selectedModel && (
        <div className="fr-col-12">
          <div className="fr-callout">
            <h3
              className="fr-callout__title"
              style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', flexWrap: 'wrap' }}
            >
              {selectedModel.label}
              <span className={`fr-badge fr-badge--sm ${TIER_COLORS[selectedModel.tier]}`}>
                {TIER_LABELS[selectedModel.tier]}
              </span>
              <span
                className="fr-text--sm"
                style={{ color: 'var(--text-mention-grey)', fontWeight: 400 }}
              >
                {selectedModel.family}
              </span>
            </h3>
            <p className="fr-callout__text">{selectedModel.shortPitch}</p>
            <div style={{ display: 'flex', gap: '1.5rem', fontSize: '0.875rem', marginBottom: '0.75rem' }}>
              <span>
                Vitesse : <Indicator value={selectedModel.latency} />
              </span>
              <span>
                Coût tokens : <Indicator value={selectedModel.cost} />
              </span>
            </div>
            {(selectedModel.strengths.length > 0 || selectedModel.tradeoffs.length > 0) && (
              <div className="fr-grid-row fr-grid-row--gutters">
                {selectedModel.strengths.length > 0 && (
                  <div className="fr-col-12 fr-col-md-6">
                    <p className="fr-text--sm fr-mb-1w"><strong>Points forts</strong></p>
                    <ul className="fr-text--sm fr-mb-0">
                      {selectedModel.strengths.map((s, i) => <li key={i}>{s}</li>)}
                    </ul>
                  </div>
                )}
                {selectedModel.tradeoffs.length > 0 && (
                  <div className="fr-col-12 fr-col-md-6">
                    <p className="fr-text--sm fr-mb-1w"><strong>Limites</strong></p>
                    <ul className="fr-text--sm fr-mb-0">
                      {selectedModel.tradeoffs.map((t, i) => <li key={i}>{t}</li>)}
                    </ul>
                  </div>
                )}
              </div>
            )}
            {selectedModel.recommendedFor.length > 0 && (
              <p className="fr-text--sm fr-mb-0 fr-mt-2w">
                <strong>Recommandé pour</strong> : {selectedModel.recommendedFor.join(' · ')}
              </p>
            )}
          </div>
        </div>
      )}

      {/* ---- Température ---- */}
      <div className="fr-col-12 fr-col-md-6">
        <label className="fr-label" htmlFor="temperature">
          Température (Précis ↔ Créatif) — {draft.temperature.toFixed(1)}
        </label>
        <input
          className="fr-range"
          id="temperature"
          type="range"
          min={0}
          max={1}
          step={0.1}
          value={draft.temperature}
          onChange={(e) => update({ temperature: Number(e.target.value) })}
        />
      </div>
    </div>
  );
}

function Indicator({ value }: { value: 1 | 2 | 3 | 4 | 5 }) {
  return (
    <span style={{ letterSpacing: '2px' }}>
      {'●'.repeat(value)}
      <span style={{ opacity: 0.3 }}>{'●'.repeat(5 - value)}</span>
    </span>
  );
}
