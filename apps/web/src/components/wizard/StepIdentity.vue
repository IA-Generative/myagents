<script setup lang="ts">
import { computed } from 'vue'
import { useWizardStore } from '@/stores/wizard'
import type { Visibility } from '@/types/agent'

const wizard = useWizardStore()

const CATEGORIES = [
  { value: 'redaction', label: 'Rédaction', icon: 'fr-icon-edit-line' },
  { value: 'juridique', label: 'Juridique', icon: 'fr-icon-scales-3-line' },
  { value: 'rh', label: 'Ressources humaines', icon: 'fr-icon-team-line' },
  { value: 'securite', label: 'Sécurité', icon: 'fr-icon-shield-line' },
  { value: 'immigration', label: 'Immigration', icon: 'fr-icon-global-line' },
  { value: 'prefecture', label: 'Préfecture', icon: 'fr-icon-government-line' },
  { value: 'it', label: 'IT / Systèmes d\'information', icon: 'fr-icon-computer-line' },
  { value: 'communication', label: 'Communication', icon: 'fr-icon-chat-3-line' },
  { value: 'transverse', label: 'Transverse', icon: 'fr-icon-links-line' },
]

const selectedCategory = computed(() => CATEGORIES.find((c) => c.value === wizard.draft.config.category))

function setVisibility(v: Visibility) {
  wizard.update({ visibility: v })
  if (v !== 'community') wizard.updateConfig({ community_path: null })
}

function setCategory(value: string) {
  wizard.updateConfig({ category: value })
  wizard.update({ category: value ? [value] : [] })
}
</script>

<template>
  <div class="fr-grid-row fr-grid-row--gutters">
    <div class="fr-col-12">
      <div class="fr-input-group">
        <label class="fr-label" for="agent-name">
          Nom de l'agent
          <span class="fr-hint-text">
            Un nom court et explicite. Ex : « Rédacteur de notes CESEDA », « Assistant accueil
            préfecture ».
          </span>
        </label>
        <input
          id="agent-name"
          v-model="wizard.draft.config.name"
          class="fr-input"
          type="text"
          maxlength="60"
          placeholder="Ex : Rédacteur de notes CESEDA"
        >
      </div>
    </div>

    <div class="fr-col-12">
      <div class="fr-input-group">
        <label class="fr-label" for="agent-description">
          Description courte
          <span class="fr-hint-text">
            Visible dans le catalogue. À qui sert l'agent et pour quoi ? 280 caractères max.
          </span>
        </label>
        <textarea
          id="agent-description"
          v-model="wizard.draft.config.description"
          class="fr-input"
          rows="3"
          maxlength="280"
          placeholder="Ex : Aide à la rédaction de notes juridiques sur le CESEDA."
        />
      </div>
    </div>

    <div class="fr-col-12 fr-col-md-6">
      <div class="fr-select-group">
        <label class="fr-label" for="agent-category">
          Catégorie métier
          <span class="fr-hint-text">
            Chaque catégorie propose une icône qui sera affichée sur l'agent.
          </span>
        </label>
        <select
          id="agent-category"
          class="fr-select"
          :value="wizard.draft.config.category"
          @change="setCategory(($event.target as HTMLSelectElement).value)"
        >
          <option value="">Sélectionner une catégorie</option>
          <option v-for="c in CATEGORIES" :key="c.value" :value="c.value">{{ c.label }}</option>
        </select>
      </div>
      <div v-if="selectedCategory" class="fr-mt-2w" style="display: flex; align-items: center; gap: 0.75rem">
        <span :class="selectedCategory.icon" class="fr-icon--lg" aria-hidden="true" />
        <span class="fr-text--sm">
          Icône associée à la catégorie <strong>{{ selectedCategory.label }}</strong>
        </span>
      </div>
    </div>

    <div class="fr-col-12 fr-col-md-6">
      <fieldset class="fr-fieldset">
        <legend class="fr-fieldset__legend">Visibilité</legend>
        <div class="fr-fieldset__content">
          <div class="fr-radio-group">
            <input
              id="vis-private"
              type="radio"
              name="visibility"
              :checked="wizard.draft.visibility === 'private'"
              @change="setVisibility('private')"
            >
            <label class="fr-label" for="vis-private">
              Privé
              <span class="fr-hint-text">Visible par vous seul</span>
            </label>
          </div>
          <div class="fr-radio-group">
            <input
              id="vis-community"
              type="radio"
              name="visibility"
              :checked="wizard.draft.visibility === 'community'"
              @change="setVisibility('community')"
            >
            <label class="fr-label" for="vis-community">
              Ma communauté
              <span class="fr-hint-text">Partagé avec un groupe d'utilisateurs</span>
            </label>
          </div>
          <div class="fr-radio-group">
            <input
              id="vis-ministry"
              type="radio"
              name="visibility"
              :checked="wizard.draft.visibility === 'ministry'"
              @change="setVisibility('ministry')"
            >
            <label class="fr-label" for="vis-ministry">
              Tout le ministère
              <span class="fr-hint-text">Publication ouverte après validation</span>
            </label>
          </div>
        </div>
      </fieldset>
    </div>

    <div v-if="wizard.draft.visibility === 'community'" class="fr-col-12">
      <div class="fr-input-group">
        <label class="fr-label" for="agent-community">
          Communauté
          <span class="fr-hint-text">Nom du groupe ou du service avec lequel partager l'agent.</span>
        </label>
        <input
          id="agent-community"
          v-model="wizard.draft.config.community_path"
          class="fr-input"
          type="text"
          placeholder="Ex : DLPAJ"
        >
      </div>
    </div>
  </div>
</template>
