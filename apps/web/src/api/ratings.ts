import { api } from './client'
import type { Rating } from '@/types/agent'

export const ratingsApi = {
  list: (agentId: string) => api.get<Rating[]>(`/ratings/${agentId}`),
  rate: (agentId: string, score: number, comment?: string) =>
    api.post<Rating>(`/ratings/${agentId}`, { score, comment }),
}
