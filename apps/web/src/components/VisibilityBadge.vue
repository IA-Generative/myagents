<script setup lang="ts">
import type { Visibility } from '@/types/agent'

const props = defineProps<{ visibility: Visibility }>()

const LABELS: Record<Visibility, string> = {
  private: 'Privé',
  community: 'Communauté',
  ministry: 'Tout le ministère',
}
</script>

<template>
  <span class="fr-badge fr-badge--sm fr-badge--purple-glycine">{{ LABELS[props.visibility] }}</span>
</template>
