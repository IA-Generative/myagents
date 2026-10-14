<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import { useAgentsStore } from '@/stores/agents'
import { agentsApi } from '@/api/agents'
import StatusBadge from '@/components/StatusBadge.vue'
import VisibilityBadge from '@/components/VisibilityBadge.vue'
import OnboardingChat from '@/components/OnboardingChat.vue'
import AgentChatWidget from '@/components/AgentChatWidget.vue'

const route = useRoute()
const agentsStore = useAgentsStore()
const openChatId = ref<string | null>(null)

onMounted(() => agentsStore.fetchMine())

async function remove(id: string) {
  await agentsStore.remove(id)
}

function toggleChat(id: string) {
  openChatId.value = openChatId.value === id ? null : id
}

const savedBanner = computed(() => {
  switch (route.query.saved) {
    case 'draft':
      return { title: 'Brouillon sauvegardé', detail: "Votre agent est enregistré en brouillon. Vous pouvez l'éditer à tout moment." }
    case 'published':
      return { title: 'Agent publié dans votre espace', detail: 'Votre agent est visible dans votre liste personnelle.' }
    case 'submitted':
      return { title: 'Agent soumis au catalogue', detail: 'Votre agent sera revu avant publication dans le catalogue.' }
    case 'updated':
      return { title: 'Agent mis à jour', detail: 'Les modifications ont été enregistrées. Une nouvelle version a été créée.' }
    default:
      return null
  }
})
</script>

<template>
  <div>
    <div class="fr-mb-4w">
      <h1>Bienvenue</h1>
      <p class="fr-text--lead">
        Mes Agents vous permet de créer et partager vos propres agents IA en quelques minutes,
        sans écrire une ligne de code.
      </p>
    </div>

    <div v-if="savedBanner" class="fr-alert fr-alert--success fr-mb-4w">
      <h3 class="fr-alert__title">{{ savedBanner.title }}</h3>
      <p>{{ savedBanner.detail }}</p>
    </div>

    <h2 class="fr-h3">Que souhaitez-vous faire&nbsp;?</h2>
    <div class="fr-grid-row fr-grid-row--gutters fr-mb-6w">
      <div class="fr-col-12 fr-col-md-4">
        <div class="fr-tile fr-enlarge-link">
          <div class="fr-tile__body">
            <div class="fr-tile__content">
              <h3 class="fr-tile__title">
                <RouterLink class="fr-tile__link" :to="{ name: 'agent-new' }">
                  {{ agentsStore.items.length === 0 ? 'Créer mon premier agent' : 'Créer un nouvel agent' }}
                </RouterLink>
              </h3>
              <p class="fr-tile__desc">
                Un formulaire guidé en 4 étapes : identité, comportement, connaissances, test.
                L'IA vous aide à rédiger le prompt.
              </p>
            </div>
          </div>
          <div class="fr-tile__header">
            <div class="fr-tile__pictogram">
              <span class="fr-icon-add-circle-line fr-icon--lg" aria-hidden="true" />
            </div>
          </div>
        </div>
      </div>
      <div class="fr-col-12 fr-col-md-4">
        <div class="fr-tile fr-enlarge-link">
          <div class="fr-tile__body">
            <div class="fr-tile__content">
              <h3 class="fr-tile__title">
                <RouterLink class="fr-tile__link" :to="{ name: 'catalog' }">Explorer le catalogue</RouterLink>
              </h3>
              <p class="fr-tile__desc">
                Parcourez les agents partagés par les autres directions. Vous pouvez les utiliser
                directement ou les dupliquer pour les personnaliser.
              </p>
            </div>
          </div>
          <div class="fr-tile__header">
            <div class="fr-tile__pictogram">
              <span class="fr-icon-search-line fr-icon--lg" aria-hidden="true" />
            </div>
          </div>
        </div>
      </div>
      <div class="fr-col-12 fr-col-md-4">
        <div class="fr-tile fr-enlarge-link">
          <div class="fr-tile__body">
            <div class="fr-tile__content">
              <h3 class="fr-tile__title">
                <RouterLink class="fr-tile__link" :to="{ name: 'agent-new' }">Partir d'un exemple</RouterLink>
              </h3>
              <p class="fr-tile__desc">
                Choisissez un modèle métier pré-configuré (préfecture, juridique, RH,
                communication) comme point de départ.
              </p>
            </div>
          </div>
          <div class="fr-tile__header">
            <div class="fr-tile__pictogram">
              <span class="fr-icon-lightbulb-line fr-icon--lg" aria-hidden="true" />
            </div>
          </div>
        </div>
      </div>
    </div>

    <section class="fr-mb-4w">
      <h2 class="fr-h3">Mes agents ({{ agentsStore.items.length }})</h2>

      <p v-if="agentsStore.loading">Chargement...</p>
      <div v-else-if="agentsStore.items.length === 0" class="fr-notice fr-notice--info">
        <div class="fr-container">
          <div class="fr-notice__body">
            <p class="fr-notice__title">Vous n'avez pas encore créé d'agent.</p>
            <p class="fr-notice__desc">
              Commencez par définir ce que votre agent doit faire et à qui il s'adresse.
              L'assistant de rédaction vous guidera à chaque étape.
            </p>
          </div>
        </div>
      </div>

      <div v-else class="fr-grid-row fr-grid-row--gutters">
        <div v-for="agent in agentsStore.items" :key="agent.id" class="fr-col-12 fr-col-md-6 fr-col-lg-4">
          <div
            style="
              border: 1px solid var(--border-default-grey);
              border-radius: 8px;
              padding: 1.25rem;
              display: flex;
              flex-direction: column;
              height: 100%;
              min-height: 320px;
            "
          >
            <h3 class="fr-h6 fr-mb-1w" style="margin: 0; line-height: 1.3; min-height: 2.6em">
              {{ agent.name || '(sans nom)' }}
            </h3>
            <div style="display: flex; flex-wrap: wrap; gap: 0.5rem; margin-bottom: 0.75rem">
              <StatusBadge :status="agent.status" />
              <VisibilityBadge :visibility="agent.visibility" />
              <span v-for="cat in agent.category" :key="cat" class="fr-badge fr-badge--sm fr-badge--purple-glycine">
                {{ cat }}
              </span>
            </div>
            <p class="fr-text--xs fr-mb-2w" style="color: var(--text-mention-grey)">
              Version {{ agent.version }} · mis à jour le {{ new Date(agent.updated_at).toLocaleString('fr-FR') }}
            </p>

            <div style="margin-top: auto; display: flex; flex-direction: column; gap: 0.5rem">
              <button
                v-if="agent.status !== 'draft'"
                type="button"
                class="fr-btn fr-btn--icon-left fr-icon-chat-3-line"
                :class="openChatId === agent.id ? 'fr-btn--secondary' : ''"
                style="width: 100%; justify-content: center"
                @click="toggleChat(agent.id)"
              >
                {{ openChatId === agent.id ? 'Fermer le chat' : 'Utiliser dans le chat' }}
              </button>
              <span
                v-else
                class="fr-btn fr-btn--icon-left fr-icon-chat-3-line"
                style="width: 100%; justify-content: center; opacity: 0.5; pointer-events: none"
                aria-disabled="true"
              >
                Publiez pour utiliser dans le chat
              </span>

              <div v-if="openChatId === agent.id" class="fr-p-2w" style="border: 1px solid var(--border-default-grey); border-radius: 8px">
                <AgentChatWidget
                  :agent-name="agent.name || 'Agent'"
                  :send="(msgs) => agentsApi.chat(agent.id, msgs)"
                />
              </div>

              <div style="display: flex; justify-content: space-between; align-items: center; margin-top: 0.5rem">
                <button class="fr-btn fr-btn--tertiary fr-btn--sm" @click="remove(agent.id)">Archiver</button>
                <RouterLink
                  class="fr-btn fr-btn--tertiary-no-outline fr-btn--sm fr-icon-edit-line"
                  :to="{ name: 'agent-edit', params: { id: agent.id } }"
                >
                  Modifier
                </RouterLink>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>

    <OnboardingChat />
  </div>
</template>
