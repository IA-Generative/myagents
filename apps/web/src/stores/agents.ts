import { defineStore } from 'pinia'
import { agentsApi } from '@/api/agents'
import type { AgentCreatePayload, AgentDetail, AgentListItem, AgentUpdatePayload } from '@/types/agent'

export const useAgentsStore = defineStore('agents', {
  state: () => ({
    items: [] as AgentListItem[],
    loading: false,
  }),
  actions: {
    async fetchMine() {
      this.loading = true
      try {
        this.items = await agentsApi.list()
      } finally {
        this.loading = false
      }
    },
    async create(payload: AgentCreatePayload): Promise<AgentDetail> {
      const created = await agentsApi.create(payload)
      await this.fetchMine()
      return created
    },
    async update(id: string, payload: AgentUpdatePayload): Promise<AgentDetail> {
      const updated = await agentsApi.update(id, payload)
      await this.fetchMine()
      return updated
    },
    async remove(id: string) {
      await agentsApi.remove(id)
      this.items = this.items.filter((a) => a.id !== id)
    },
  },
})
