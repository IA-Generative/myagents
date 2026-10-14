<script setup lang="ts">
import { computed } from 'vue'
import { agentsApi } from '@/api/agents'
import { useWizardStore } from '@/stores/wizard'
import AgentChatWidget from '@/components/AgentChatWidget.vue'

const props = defineProps<{ agentId: string | null }>()
const emit = defineEmits<{ publish: [status: 'draft' | 'published' | 'submitted'] }>()

const wizard = useWizardStore()

const isValid = computed(
  () => wizard.draft.config.name.trim().length > 0 && wizard.draft.config.system_prompt.trim().length > 0,
)

const visibilityLabel = computed(() => {
  const v = wizard.draft.visibility
  if (v === 'private') return 'Privé'
  if (v === 'community') return `Communauté ${wizard.draft.config.community_path ?? '(non choisie)'}`
  return 'Tout le ministère'
})

const promptExcerpt = computed(() => {
  const prompt = wizard.draft.config.system_prompt
  if (!prompt) return null
  return prompt.length > 200 ? `${prompt.slice(0, 200)}…` : prompt
})

function chat(messages: { role: string; content: string }[]) {
  if (!props.agentId) return Promise.reject(new Error('no agent id'))
  return agentsApi.chat(props.agentId, messages)
}
</script>

<template>
  <div class="fr-grid-row fr-grid-row--gutters">
    <div class="fr-col-12">
      <div class="fr-callout">
        <h3 class="fr-callout__title">Récapitulatif de votre agent</h3>
        <dl class="fr-mb-0">
          <dt><strong>Nom :</strong></dt>
          <dd>{{ wizard.draft.config.name || '(non renseigné)' }}</dd>
          <dt class="fr-mt-1w"><strong>Description :</strong></dt>
          <dd>{{ wizard.draft.config.description || '(non renseigné)' }}</dd>
          <dt class="fr-mt-1w"><strong>Visibilité :</strong></dt>
          <dd>{{ visibilityLabel }}</dd>
          <dt class="fr-mt-1w"><strong>Modèle :</strong></dt>
          <dd>{{ wizard.draft.config.model_id }}</dd>
          <dt class="fr-mt-1w"><strong>Prompt système :</strong></dt>
          <dd>{{ promptExcerpt ?? '(non renseigné)' }}</dd>
        </dl>
      </div>
    </div>

    <div class="fr-col-12 fr-col-md-6">
      <h3>Tester l'agent</h3>
      <AgentChatWidget
        v-if="agentId"
        :agent-name="wizard.draft.config.name || 'Agent'"
        :greeting="wizard.draft.config.greeting"
        :send="chat"
      />
      <p v-else class="fr-hint-text">Enregistrez d'abord un brouillon pour pouvoir tester l'agent.</p>
    </div>

    <div class="fr-col-12 fr-col-md-6">
      <h3>Publication</h3>
      <div class="fr-btns-group">
        <button
          type="button"
          class="fr-btn fr-btn--secondary"
          :disabled="!isValid"
          @click="emit('publish', 'draft')"
        >
          Sauvegarder en brouillon
        </button>
        <button
          type="button"
          class="fr-btn"
          :disabled="!isValid"
          @click="emit('publish', 'published')"
        >
          Publier dans mon espace
        </button>
        <button
          type="button"
          class="fr-btn fr-btn--tertiary"
          :disabled="!isValid || wizard.draft.visibility !== 'ministry'"
          :title="
            wizard.draft.visibility !== 'ministry'
              ? 'Disponible uniquement si la visibilité est « Tout le ministère »'
              : undefined
          "
          @click="emit('publish', 'submitted')"
        >
          Proposer au catalogue
        </button>
      </div>
      <p v-if="!isValid" class="fr-text--sm fr-mt-2w">
        Remplissez au moins le <strong>nom</strong> (étape 1) et les
        <strong>instructions système</strong> (étape 2) pour pouvoir publier.
      </p>
    </div>
  </div>
</template>
