<script setup lang="ts">
defineProps<{
  steps: string[]
  current: number
}>()
</script>

<template>
  <div class="fr-stepper">
    <h2 class="fr-stepper__title">
      {{ steps[current - 1] }}
      <span class="fr-stepper__state">Étape {{ current }} sur {{ steps.length }}</span>
    </h2>
    <div class="fr-stepper__steps" :data-fr-current-step="current" :data-fr-steps="steps.length" />
  </div>
</template>
