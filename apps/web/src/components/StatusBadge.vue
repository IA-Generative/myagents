<script setup lang="ts">
import type { AgentStatus } from '@/types/agent'

const props = defineProps<{ status: AgentStatus }>()

const LABELS: Record<AgentStatus, string> = {
  draft: 'Brouillon',
  published: 'Publié',
  submitted: 'Soumis au catalogue',
  archived: 'Archivé',
}

const COLORS: Record<AgentStatus, string> = {
  draft: 'fr-badge--yellow-tournesol',
  published: 'fr-badge--green-emeraude',
  submitted: 'fr-badge--blue-cumulus',
  archived: 'fr-badge--grey',
}
</script>

<template>
  <span class="fr-badge fr-badge--sm" :class="COLORS[props.status]">{{ LABELS[props.status] }}</span>
</template>
