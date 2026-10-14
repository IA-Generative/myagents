<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'

const route = useRoute()
const title = computed(() => String(route.meta.title ?? ''))
</script>

<template>
  <div class="fr-container fr-py-6w">
    <h1>{{ title }}</h1>
    <!-- Le contenu juridique doit être fourni par l'éditeur du service. -->
    <p>Cette page n'a pas encore été renseignée par l'éditeur du service.</p>
  </div>
</template>
