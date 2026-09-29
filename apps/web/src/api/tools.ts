import { api } from './client'
import type { ToolProfile } from '@/types/agent'

export const toolsApi = {
  list: () => api.get<ToolProfile[]>('/agents/tools'),
}
