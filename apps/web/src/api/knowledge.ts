import { api } from './client'
import type { KnowledgeBase, KnowledgeDocument } from '@/types/agent'

export const knowledgeApi = {
  list: () => api.get<KnowledgeBase[]>('/knowledge'),
  create: (name: string) => api.post<KnowledgeBase>('/knowledge', { name }),
  remove: (id: string) => api.delete<{ id: string }>(`/knowledge/${id}`),
  uploadDocument: (id: string, file: File) => {
    const form = new FormData()
    form.append('file', file)
    return api.postForm<KnowledgeDocument>(`/knowledge/${id}/documents`, form)
  },
}
