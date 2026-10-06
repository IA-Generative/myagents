<script setup lang="ts">
import { onMounted, watch } from 'vue'
import { RouterView } from 'vue-router'
import { annoncerIdentite } from '@/menuCommun'
import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()

// Le compte (nom, déconnexion) est porté par le menu commun de la bêta : on lui passe
// l'identité dès qu'elle est connue, l'en-tête n'affiche plus de liens de compte.
watch(
  () => auth.user,
  (user) => annoncerIdentite(user),
  { immediate: true },
)

onMounted(() => {
  if (!auth.user) auth.init()
})
</script>

<template>
  <!-- Icône de Mes agents en logo d'opérateur, reprise de l'application Next.js (public/favicon.svg). -->
  <DsfrHeader
    service-title="Mes Agents"
    service-tagline="Créez et partagez vos agents IA"
    :logo-text="['République', 'Française']"
    operator-img-src="/mes-agents.svg"
    operator-img-alt="Mes agents"
    :operator-img-style="{ maxHeight: '40px', width: 'auto' }"
  />
  <main class="fr-container fr-py-6w">
    <RouterView />
  </main>
  <DsfrFooter :logo-text="['République', 'Française']" />
</template>
