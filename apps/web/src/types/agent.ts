export type Visibility = 'private' | 'community' | 'ministry'
export type AgentStatus = 'draft' | 'published' | 'submitted' | 'archived'

export interface ConfigSnapshot {
  name: string
  description: string
  category: string
  community_path: string | null
  system_prompt: string
  greeting: string
  examples: string[]
  model_id: string
  temperature: number
  knowledge_ids: string[]
  tool_ids: string[]
  // Contrat d'agents MirAI : sur quoi l'agent sait travailler, et ce qu'il rend.
  inputs: AgentInput[]
  outputs: AgentOutput[]
}

export const AGENT_INPUTS = [
  'text',
  'selection',
  'document',
  'email',
  'thread',
  'meeting',
  'collection',
  'page',
] as const
export type AgentInput = (typeof AGENT_INPUTS)[number]

export const AGENT_OUTPUTS = ['text', 'replacement', 'insertion'] as const
export type AgentOutput = (typeof AGENT_OUTPUTS)[number]

export interface AgentListItem {
  id: string
  creator_id: string
  name: string
  model_ref: string
  visibility: Visibility
  status: AgentStatus
  category: string[]
  tags: string[]
  version: number
  created_at: string
  updated_at: string
}

export interface AgentDetail extends AgentListItem {
  config: ConfigSnapshot
}

export interface AgentCreatePayload {
  visibility: Visibility
  status: AgentStatus
  category: string[]
  tags: string[]
  config: ConfigSnapshot
}

export type AgentUpdatePayload = Partial<
  Pick<AgentCreatePayload, 'visibility' | 'status' | 'category' | 'tags'>
> & { config: ConfigSnapshot; changelog?: string }

export interface ModelProfile {
  id: string
  label: string
  tier: string
  short_pitch: string
}

export interface ToolProfile {
  id: string
  label: string
  description: string
}

export type DocumentStatus = 'pending' | 'indexed' | 'failed'

export interface KnowledgeDocument {
  id: string
  knowledge_base_id: string
  filename: string
  char_count: number
  status: DocumentStatus
  created_at: string
}

export interface KnowledgeBase {
  id: string
  creator_id: string
  name: string
  created_at: string
  documents: KnowledgeDocument[]
}

export interface Rating {
  id: string
  agent_id: string
  score: number
  comment: string | null
  created_at: string
}

export interface Favorite {
  id: string
  agent_id: string
  created_at: string
}

export interface OnboardingAgentConfig {
  ready: boolean
  name: string
  description: string
  category: string
  system_prompt: string
  greeting: string
  examples: string[]
}

export interface OnboardingMessage {
  role: 'user' | 'assistant'
  content: string
}
