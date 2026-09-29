import { api } from './client'
import type { ModelProfile } from '@/types/agent'

export const modelsApi = {
  list: () => api.get<ModelProfile[]>('/models'),
}
