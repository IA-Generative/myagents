import { api } from './client'
import type { AgentDetail, AgentListItem } from '@/types/agent'

export const catalogApi = {
  list: (category?: string) =>
    api.get<AgentListItem[]>(`/catalog${category ? `?category=${encodeURIComponent(category)}` : ''}`),
  get: (id: string) => api.get<AgentDetail>(`/catalog/${id}`),
  chat: (id: string, messages: { role: string; content: string }[]) =>
    api.post<{ reply: string }>(`/catalog/${id}/chat`, { messages }),
}
