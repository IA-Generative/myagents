<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { RouterView } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()

const quickLinks = computed(() => {
  if (!auth.isAuthenticated) return []
  const links: { label: string; to?: string; button?: boolean; onClick?: () => void }[] = [
    {
      label: auth.user?.username ?? 'Utilisateur',
      to: '/agents',
    },
  ]
  // Sans SSO l'identité est un substitut de dev : se déconnecter n'aurait aucun effet.
  if (auth.ssoEnabled) {
    links.push({ label: 'Déconnexion', button: true, onClick: () => auth.logout() })
  }
  return links
})

onMounted(() => {
  if (!auth.user) auth.init()
})
</script>

<template>
  <DsfrHeader
    service-title="Mes Agents"
    service-tagline="Créez et partagez vos agents IA"
    :logo-text="['République', 'Française']"
    :quick-links="quickLinks"
  />
  <main class="fr-container fr-py-6w">
    <RouterView />
  </main>
  <DsfrFooter :logo-text="['République', 'Française']" />
</template>
