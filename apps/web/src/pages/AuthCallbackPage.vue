<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const auth = useAuthStore()
const error = ref<string | null>(null)

onMounted(async () => {
  try {
    const returnPath = await auth.handleCallback()
    router.replace(returnPath || '/')
  } catch (e: unknown) {
    error.value = e instanceof Error ? e.message : 'Erreur lors de la connexion'
  }
})
</script>

<template>
  <div class="fr-container fr-py-8w">
    <div class="fr-grid-row fr-grid-row--center">
      <div class="fr-col-12 fr-col-md-6">
        <div v-if="error" class="fr-alert fr-alert--error">
          <h3 class="fr-alert__title">Connexion échouée</h3>
          <p>{{ error }}</p>
        </div>
        <div v-else class="fr-alert fr-alert--info">
          <h3 class="fr-alert__title">Connexion en cours…</h3>
          <p>Redirection automatique après authentification.</p>
        </div>
      </div>
    </div>
  </div>
</template>
