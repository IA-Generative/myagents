// Page d'edition d'un agent existant — reutilise le wizard avec le draft
// hydrate depuis le snapshot Prisma. Le PUT /api/ab/agents/:id cree une
// nouvelle version.

'use client';

import { Suspense, useEffect, useMemo, useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { WizardProvider, type AgentDraft } from '../../new/_context';
import { StepIdentity } from '../../new/_components/step-identity';
import { StepBehavior } from '../../new/_components/step-behavior';
import { StepKnowledge } from '../../new/_components/step-knowledge';
import { useWizard } from '../../new/_context';

const STEPS = [
  { id: 1, title: 'Identite' },
  { id: 2, title: 'Comportement' },
  { id: 3, title: 'Connaissances et outils' },
  { id: 4, title: 'Enregistrer' },
] as const;

export default function EditAgentPage() {
  return (
    <Suspense fallback={<div className="fr-container fr-py-4w">Chargement...</div>}>
      <EditAgentInner />
    </Suspense>
  );
}

function EditAgentInner() {
  const { id } = useParams<{ id: string }>();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [initialDraft, setInitialDraft] = useState<Partial<AgentDraft> | null>(null);

  useEffect(() => {
    fetch(`/api/ab/agents/${id}`)
      .then(async (r) => {
        if (!r.ok) throw new Error(`${r.status}`);
        const data = await r.json();
        const cfg = data.config ?? {};
        setInitialDraft({
          name: cfg.name ?? '',
          description: cfg.description ?? '',
          category: cfg.category ?? '',
          visibility: cfg.visibility ?? 'private',
          communityPath: cfg.communityPath ?? null,
          systemPrompt: cfg.systemPrompt ?? '',
          greeting: cfg.greeting ?? '',
          examples: Array.isArray(cfg.examples) ? cfg.examples : [],
          modelId: cfg.modelId ?? 'mistral-small-3.2-24b-instruct-2506',
          temperature: cfg.temperature ?? 0.7,
        });
      })
      .catch((err) => setError(String(err)))
      .finally(() => setLoading(false));
  }, [id]);

  if (loading) return <div className="fr-container fr-py-4w">Chargement de l&apos;agent...</div>;
  if (error) return <div className="fr-alert fr-alert--error"><p>Erreur : {error}</p></div>;
  if (!initialDraft) return null;

  return (
    <WizardProvider initialDraft={initialDraft}>
      <EditWizardShell agentId={id} />
    </WizardProvider>
  );
}

function EditWizardShell({ agentId }: { agentId: string }) {
  const router = useRouter();
  const { draft, promptValidated } = useWizard();
  const [currentStep, setCurrentStep] = useState(1);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Gate identique au wizard de création : on ne quitte l'étape Comportement
  // qu'après validation anti-jailbreak des instructions système.
  const nextBlocked = currentStep === 2 && !promptValidated;

  async function save() {
    setBusy(true);
    setError(null);
    try {
      const res = await fetch(`/api/ab/agents/${agentId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(draft),
      });
      if (!res.ok) {
        const d = await res.json().catch(() => ({}));
        setError(d.message ?? `Erreur ${res.status} : ${d.error ?? 'inconnue'}`);
        setBusy(false);
        return;
      }
      router.push('/agents?saved=updated');
    } catch (err) {
      setError(String(err));
      setBusy(false);
    }
  }

  return (
    <div>
      <h1>Modifier l&apos;agent</h1>

      <div className="fr-stepper">
        <h2 className="fr-stepper__title">
          {STEPS[currentStep - 1].title}
          <span className="fr-stepper__state">
            Etape {currentStep} sur {STEPS.length}
          </span>
        </h2>
        <div
          className="fr-stepper__steps"
          data-fr-current-step={currentStep}
          data-fr-steps={STEPS.length}
        />
      </div>

      <section className="fr-mt-4w">
        {currentStep === 1 && <StepIdentity />}
        {currentStep === 2 && <StepBehavior />}
        {currentStep === 3 && <StepKnowledge />}
        {currentStep === 4 && (
          <div>
            <div className="fr-callout fr-mb-4w">
              <h3 className="fr-callout__title">Recapitulatif</h3>
              <dl>
                <dt><strong>Nom :</strong></dt>
                <dd>{draft.name || <em>(vide)</em>}</dd>
                <dt className="fr-mt-1w"><strong>Modele :</strong></dt>
                <dd>{draft.modelId}</dd>
                <dt className="fr-mt-1w"><strong>Prompt :</strong></dt>
                <dd>{draft.systemPrompt ? `${draft.systemPrompt.slice(0, 200)}...` : <em>(vide)</em>}</dd>
              </dl>
            </div>
            <div className="fr-btns-group">
              <button
                className="fr-btn"
                disabled={busy || !draft.name || !draft.systemPrompt}
                onClick={save}
              >
                {busy ? 'Enregistrement...' : 'Enregistrer les modifications'}
              </button>
            </div>
            {error && (
              <div className="fr-alert fr-alert--error fr-alert--sm fr-mt-2w">
                <p>{error}</p>
              </div>
            )}
          </div>
        )}
      </section>

      <div className="fr-btns-group fr-btns-group--inline fr-mt-4w">
        <button
          type="button"
          className="fr-btn fr-btn--secondary"
          disabled={currentStep === 1}
          onClick={() => setCurrentStep((s) => Math.max(1, s - 1))}
        >
          Precedent
        </button>
        <button
          type="button"
          className="fr-btn"
          disabled={currentStep === STEPS.length || nextBlocked}
          onClick={() => setCurrentStep((s) => Math.min(STEPS.length, s + 1))}
        >
          Suivant
        </button>
      </div>
      {nextBlocked && (
        <p className="fr-hint-text fr-mt-1w">
          Validez les instructions système pour continuer.
        </p>
      )}
    </div>
  );
}
