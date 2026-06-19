// Contexte React partagé par les 4 étapes du wizard de création d'agent.
// Stocke toute la config du brouillon dans un unique useState, exposé via
// un hook useWizard(). Évite de lifter manuellement des dizaines de props
// à travers les étapes.

'use client';

import { createContext, useContext, useState, useCallback, type ReactNode } from 'react';
import { DEFAULT_MODEL_ID } from '@/lib/models';

export type AgentVisibility = 'private' | 'community' | 'ministry';

export type AgentDraft = {
  // Étape 1 — Identité
  name: string;
  description: string;
  category: string;
  visibility: AgentVisibility;
  communityPath: string | null;

  // Étape 2 — Comportement
  systemPrompt: string;
  greeting: string;
  examples: string[];
  modelId: string;
  temperature: number;
};

const INITIAL: AgentDraft = {
  name: '',
  description: '',
  category: '',
  visibility: 'private',
  communityPath: null,
  systemPrompt: '',
  greeting: '',
  examples: [],
  modelId: DEFAULT_MODEL_ID,
  temperature: 0.7,
};

type WizardContextValue = {
  draft: AgentDraft;
  update: (patch: Partial<AgentDraft>) => void;
  reset: () => void;
  /**
   * Drapeau transient (non persisté) : true quand les instructions système
   * courantes ont passé la validation anti-jailbreak. Toute modification du
   * systemPrompt le repasse à false (cf. update), forçant une re-validation.
   */
  promptValidated: boolean;
  setPromptValidated: (v: boolean) => void;
};

const WizardContext = createContext<WizardContextValue | null>(null);

export function WizardProvider({
  children,
  initialDraft,
}: {
  children: ReactNode;
  initialDraft?: Partial<AgentDraft>;
}) {
  const [draft, setDraft] = useState<AgentDraft>({ ...INITIAL, ...initialDraft });
  const [promptValidated, setPromptValidated] = useState(false);

  const update = useCallback((patch: Partial<AgentDraft>) => {
    setDraft((d) => ({ ...d, ...patch }));
    // Toute modification des instructions système invalide la validation.
    if ('systemPrompt' in patch) setPromptValidated(false);
  }, []);

  const reset = useCallback(() => {
    setDraft(INITIAL);
    setPromptValidated(false);
  }, []);

  const value: WizardContextValue = {
    draft,
    update,
    reset,
    promptValidated,
    setPromptValidated,
  };
  return <WizardContext.Provider value={value}>{children}</WizardContext.Provider>;
}

export function useWizard(): WizardContextValue {
  const ctx = useContext(WizardContext);
  if (!ctx) {
    throw new Error('useWizard doit être utilisé dans <WizardProvider>');
  }
  return ctx;
}
