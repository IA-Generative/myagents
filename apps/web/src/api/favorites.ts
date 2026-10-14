import { api } from './client'
import type { Favorite } from '@/types/agent'

export const favoritesApi = {
  list: () => api.get<Favorite[]>('/favorites'),
  add: (agentId: string) => api.post<Favorite>(`/favorites/${agentId}`),
  remove: (agentId: string) => api.delete<{ agent_id: string; removed: boolean }>(`/favorites/${agentId}`),
}
