import { api, streamChat, type StreamChatCallbacks } from './client'
import type { AgentDetail, AgentListItem, ChatResponse } from '@/types/agent'

export const catalogApi = {
  list: (category?: string) =>
    api.get<AgentListItem[]>(`/catalog${category ? `?category=${encodeURIComponent(category)}` : ''}`),
  get: (id: string) => api.get<AgentDetail>(`/catalog/${id}`),
  chat: (id: string, messages: { role: string; content: string }[], conversationId?: string) =>
    api.post<ChatResponse>(`/catalog/${id}/chat`, { messages, conversation_id: conversationId }),
  chatStream: (
    id: string,
    messages: { role: string; content: string }[],
    callbacks: StreamChatCallbacks,
    conversationId?: string,
    signal?: AbortSignal,
  ) =>
    streamChat(
      `/catalog/${id}/chat`,
      { messages, stream: true, conversation_id: conversationId },
      callbacks,
      signal,
    ),
}
