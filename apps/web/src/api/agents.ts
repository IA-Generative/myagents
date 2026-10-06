import { api } from './client'
import type {
  AgentCreatePayload,
  AgentDetail,
  AgentListItem,
  AgentUpdatePayload,
  ConfigSnapshot,
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
  chat: (id: string, messages: { role: string; content: string }[]) =>
    api.post<{ reply: string }>(`/agents/${id}/chat`, { messages }),
  previewChat: (config: ConfigSnapshot, messages: { role: string; content: string }[]) =>
    api.post<{ reply: string }>('/agents/preview-chat', { config, messages }),
}
