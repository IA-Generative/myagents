import { defineStore } from 'pinia'
import { catalogApi } from '@/api/catalog'
import type { AgentListItem } from '@/types/agent'

export const useCatalogStore = defineStore('catalog', {
  state: () => ({
    items: [] as AgentListItem[],
    loading: false,
  }),
  actions: {
    async fetch(category?: string) {
      this.loading = true
      try {
        this.items = await catalogApi.list(category)
      } finally {
        this.loading = false
      }
    },
  },
})
