<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { RouterView } from 'vue-router'
import { annoncerIdentite } from '@/menuCommun'
import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()
const route = useRoute()
const router = useRouter()
const authError = ref<string | null>(null)

// Le compte (nom, déconnexion) est porté par le menu commun de la bêta : on lui passe
// l'identité dès qu'elle est connue, l'en-tête n'affiche plus de liens de compte.
watch(
  () => auth.user,
  (user) => annoncerIdentite(user),
  { immediate: true },
)

onMounted(() => {
  const err = route.query.auth_error as string | undefined
  if (err) {
    authError.value = err
    // Nettoyer le paramètre de l'URL sans recharger
    router.replace({ query: { ...route.query, auth_error: undefined } })
  }
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
    <DsfrAlert
      v-if="authError"
      type="error"
      title="Erreur de connexion"
      :description="authError === 'auth_unavailable'
        ? 'Le service d\'authentification est temporairement indisponible.'
        : 'Votre session a expiré ou une erreur de connexion s\'est produite.'"
      closeable
      @close="authError = null"
    >
      <template #default>
        <p>
          <a href="#" @click.prevent="auth.login()">Se reconnecter</a>
        </p>
      </template>
    </DsfrAlert>
    <RouterView />
  </main>
  <DsfrFooter :logo-text="['République', 'Française']" />
</template>
