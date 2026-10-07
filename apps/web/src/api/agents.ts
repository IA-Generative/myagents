import { api, streamChat, type StreamChatCallbacks } from './client'
import type {
  AgentCreatePayload,
  AgentDetail,
  AgentListItem,
  AgentUpdatePayload,
  ChatResponse,
  ConfigSnapshot,
  Conversation,
  ConversationMessage,
} from '@/types/agent'

export const agentsApi = {
  list: () => api.get<AgentListItem[]>('/agents'),
  create: (payload: AgentCreatePayload) => api.post<AgentDetail>('/agents', payload),
  get: (id: string) => api.get<AgentDetail>(`/agents/${id}`),
  update: (id: string, payload: AgentUpdatePayload) =>
    api.put<AgentDetail>(`/agents/${id}`, payload),
  remove: (id: string) => api.delete<{ id: string; status: string }>(`/agents/${id}`),
  fork: (id: string) => api.post<AgentDetail>(`/agents/${id}/fork`),
  submit: (id: string) => api.post<AgentDetail>(`/agents/${id}/submit`),
  chat: (id: string, messages: { role: string; content: string }[], conversationId?: string) =>
    api.post<ChatResponse>(`/agents/${id}/chat`, { messages, conversation_id: conversationId }),
  chatStream: (
    id: string,
    messages: { role: string; content: string }[],
    callbacks: StreamChatCallbacks,
    conversationId?: string,
    signal?: AbortSignal,
  ) =>
    streamChat(
      `/agents/${id}/chat`,
      { messages, stream: true, conversation_id: conversationId },
      callbacks,
      signal,
    ),
  previewChat: (config: ConfigSnapshot, messages: { role: string; content: string }[]) =>
    api.post<ChatResponse>('/agents/preview-chat', { config, messages }),
  conversations: (agentId?: string) =>
    api.get<Conversation[]>('/conversations' + (agentId ? `?agent_id=${agentId}` : '')),
  conversationMessages: (convId: string) =>
    api.get<ConversationMessage[]>(`/conversations/${convId}/messages`),
  deleteConversation: (convId: string) =>
    api.delete<{ id: string; status: string }>(`/conversations/${convId}`),
}
