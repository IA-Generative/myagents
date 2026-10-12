import { api } from './client'

export interface GroupProfile {
  id: string
  name: string
  path: string
}

export const groupsApi = {
  search: (q: string) =>
    api.get<GroupProfile[]>(`/groups${q ? '?q=' + encodeURIComponent(q) : ''}`),
}
