import { defineStore } from 'pinia'
import type { ConfigSnapshot, Visibility } from '@/types/agent'

export interface AgentDraft {
  visibility: Visibility
  category: string[]
  tags: string[]
  config: ConfigSnapshot
}

const DEFAULT_CONFIG: ConfigSnapshot = {
  name: '',
  description: '',
  category: '',
  community_path: null,
  system_prompt: '',
  greeting: '',
  examples: [],
  model_id: '',
  temperature: 0.7,
  knowledge_ids: [],
  tool_ids: [],
  inputs: ['text'],
  outputs: ['text'],
}

function initialDraft(): AgentDraft {
  return {
    visibility: 'private',
    category: [],
    tags: [],
    config: { ...DEFAULT_CONFIG },
  }
}

export const useWizardStore = defineStore('wizard', {
  state: () => ({
    draft: initialDraft(),
    // Transient flag: true once the current system prompt passed the anti-jailbreak
    // gate. Any edit to system_prompt resets it, forcing re-validation.
    promptValidated: false,
  }),
  actions: {
    update(patch: Partial<AgentDraft>) {
      this.draft = { ...this.draft, ...patch }
    },
    updateConfig(patch: Partial<ConfigSnapshot>) {
      this.draft.config = { ...this.draft.config, ...patch }
      if ('system_prompt' in patch) this.promptValidated = false
    },
    setPromptValidated(value: boolean) {
      this.promptValidated = value
    },
    reset() {
      this.draft = initialDraft()
      this.promptValidated = false
    },
    load(draft: AgentDraft) {
      this.draft = draft
      this.promptValidated = false
    },
  },
})
