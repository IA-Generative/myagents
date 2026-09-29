<script setup lang="ts">
import { RouterView } from 'vue-router'
</script>

<template>
  <DsfrHeader
    service-title="Mes Agents"
    service-tagline="Créez et partagez vos agents IA"
    :logo-text="['République', 'Française']"
    :quick-links="[]"
  />
  <main class="fr-container fr-py-6w">
    <RouterView />
  </main>
  <DsfrFooter :logo-text="['République', 'Française']" />
</template>
