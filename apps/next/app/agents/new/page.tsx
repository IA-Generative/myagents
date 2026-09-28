// Wizard de création d'agent — coquille navigable à 4 étapes (§3.1 du prompt).
// L'état complet du brouillon est dans WizardContext (voir _context.tsx) pour
// que chaque étape puisse lire/écrire sans props drilling.

'use client';

import { Suspense, useState, useMemo } from 'react';
import { useSearchParams } from 'next/navigation';
import { WizardProvider, useWizard, type AgentDraft } from './_context';
import { StepIdentity } from './_components/step-identity';
import { StepBehavior } from './_components/step-behavior';
import { StepKnowledge } from './_components/step-knowledge';
import { StepTestPublish } from './_components/step-test-publish';

const STEPS = [
  { id: 1, title: 'Identité' },
  { id: 2, title: 'Comportement' },
  { id: 3, title: 'Connaissances et outils' },
  { id: 4, title: 'Test et publication' },
] as const;

export default function NewAgentPage() {
  return (
    <Suspense fallback={<div className="fr-container fr-py-4w">Chargement...</div>}>
      <NewAgentPageInner />
    </Suspense>
  );
}

function NewAgentPageInner() {
  const searchParams = useSearchParams();

  const initialDraft = useMemo<Partial<AgentDraft>>(() => {
    const raw = searchParams.get('onboarding');
    if (!raw) return {};
    try {
      const cfg = JSON.parse(decodeURIComponent(raw));
      return {
        name: cfg.name ?? '',
        description: cfg.description ?? '',
        category: cfg.category ?? '',
        systemPrompt: cfg.systemPrompt ?? '',
        greeting: cfg.greeting ?? '',
        examples: Array.isArray(cfg.examples) ? cfg.examples : [],
      };
    } catch {
      return {};
    }
  }, [searchParams]);

  return (
    <WizardProvider initialDraft={initialDraft}>
      <WizardShell fromOnboarding={Object.keys(initialDraft).length > 0} />
    </WizardProvider>
  );
}

function WizardShell({ fromOnboarding = false }: { fromOnboarding?: boolean }) {
  const [currentStep, setCurrentStep] = useState(1);
  const { promptValidated } = useWizard();

  // L'étape 2 (Comportement) ne peut être quittée que si les instructions
  // système ont été validées par le module anti-jailbreak.
  const nextBlocked = currentStep === 2 && !promptValidated;

  return (
    <div>
      <h1>Créer un agent</h1>
      {fromOnboarding && (
        <div className="fr-alert fr-alert--info fr-mb-4w">
          <p>
            L&apos;assistant a pré-rempli les champs à partir de vos réponses.
            Vérifiez et ajustez si nécessaire, puis passez à l&apos;étape suivante.
          </p>
        </div>
      )}

      {/* Stepper DSFR */}
      <div className="fr-stepper">
        <h2 className="fr-stepper__title">
          {STEPS[currentStep - 1].title}
          <span className="fr-stepper__state">
            Étape {currentStep} sur {STEPS.length}
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
        {currentStep === 4 && <StepTestPublish />}
      </section>

      <div className="fr-btns-group fr-btns-group--inline fr-mt-4w">
        <button
          type="button"
          className="fr-btn fr-btn--secondary"
          disabled={currentStep === 1}
          onClick={() => setCurrentStep((s) => Math.max(1, s - 1))}
        >
          Précédent
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
