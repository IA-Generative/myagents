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
}

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
  progress: string[]
}

export interface OnboardingMessage {
  role: 'user' | 'assistant'
  content: string
}

export interface RefineConfigRequest {
  config: ConfigSnapshot
  feedback: string
}

export interface RefineConfigResponse {
  config: ConfigSnapshot
  message: string
}

export interface ChatResponse {
  reply: string
  conversation_id?: string | null
  message_id?: string | null
}

export interface Citation {
  filename: string
  document_id: string
  chunk_id: string
  score: number
  snippet: string
}

export interface ToolStep {
  tool_name: string
  args: Record<string, unknown>
  result: string
  status: string
}

export interface Conversation {
  id: string
  agent_id: string
  title: string
  created_at: string
  updated_at: string
  last_message_at: string | null
}

export interface ConversationMessage {
  id: string
  role: 'user' | 'assistant' | 'tool' | 'system'
  content: string
  tool_calls: Record<string, unknown> | null
  tool_call_id: string | null
  metadata: Record<string, unknown> | null
  created_at: string
}
