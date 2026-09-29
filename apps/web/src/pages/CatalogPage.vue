<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { RouterLink } from 'vue-router'
import { catalogApi } from '@/api/catalog'
import VisibilityBadge from '@/components/VisibilityBadge.vue'
import type { AgentListItem } from '@/types/agent'

const agents = ref<AgentListItem[]>([])
const loading = ref(true)

onMounted(async () => {
  try {
    agents.value = await catalogApi.list()
  } finally {
    loading.value = false
  }
})
</script>

<template>
  <div>
    <h1>Catalogue des agents</h1>
    <p class="fr-text--lead">
      Découvrez les agents publiés par les autres directions et par défaut, testez-les
      directement dans le chat, ou dupliquez-les pour créer votre propre version.
    </p>

    <p v-if="loading">Chargement...</p>
    <div v-else-if="agents.length === 0" class="fr-notice fr-notice--info">
      <div class="fr-container">
        <div class="fr-notice__body">
          <p class="fr-notice__title">Aucun agent publié pour le moment.</p>
        </div>
      </div>
    </div>

    <div v-else class="fr-grid-row fr-grid-row--gutters">
      <div v-for="agent in agents" :key="agent.id" class="fr-col-12 fr-col-md-6 fr-col-lg-4">
        <div class="fr-tile fr-enlarge-link">
          <div class="fr-tile__body">
            <div class="fr-tile__content">
              <h3 class="fr-tile__title">
                <RouterLink class="fr-tile__link" :to="{ name: 'catalog-detail', params: { id: agent.id } }">
                  {{ agent.name || '(sans nom)' }}
                </RouterLink>
              </h3>
              <div style="display: flex; flex-wrap: wrap; gap: 0.5rem; margin-bottom: 0.5rem">
                <VisibilityBadge :visibility="agent.visibility" />
                <span v-for="cat in agent.category" :key="cat" class="fr-badge fr-badge--sm fr-badge--purple-glycine">
                  {{ cat }}
                </span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <h2 class="fr-h3 fr-mt-6w">Ou bien&nbsp;:</h2>
    <div class="fr-grid-row fr-grid-row--gutters">
      <div class="fr-col-12 fr-col-md-6">
        <div class="fr-tile fr-enlarge-link">
          <div class="fr-tile__body">
            <div class="fr-tile__content">
              <h3 class="fr-tile__title">
                <RouterLink class="fr-tile__link" :to="{ name: 'agent-new' }">
                  Créer votre propre agent
                </RouterLink>
              </h3>
              <p class="fr-tile__desc">
                Lancez l'assistant guidé pour créer un agent personnalisé en quelques minutes.
              </p>
            </div>
          </div>
        </div>
      </div>
      <div class="fr-col-12 fr-col-md-6">
        <div class="fr-tile fr-enlarge-link">
          <div class="fr-tile__body">
            <div class="fr-tile__content">
              <h3 class="fr-tile__title">
                <RouterLink class="fr-tile__link" :to="{ name: 'agents' }">Voir mes agents</RouterLink>
              </h3>
              <p class="fr-tile__desc">
                Retrouvez les agents que vous avez créés, leurs statistiques et leurs versions.
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
