<script setup lang="ts">
import { computed, nextTick, onUnmounted, ref, watch } from 'vue'
import { useWizardStore } from '@/stores/wizard'
import type { Visibility } from '@/types/agent'
import { groupsApi, type GroupProfile } from '@/api/groups'

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

// --- Combobox de recherche de groupes ---
const groupQuery = ref('')
const groupResults = ref<GroupProfile[]>([])
const groupOpen = ref(false)
const groupLoading = ref(false)
const groupError = ref(false)
const activeIndex = ref(-1)
const comboboxRef = ref<HTMLElement | null>(null)
const searchInputRef = ref<HTMLInputElement | null>(null)
let debounceId: ReturnType<typeof setTimeout> | null = null
let requestId = 0

const selectedGroupPath = computed(() => wizard.draft.config.community_path)

watch(groupQuery, (q, _old, onCleanup) => {
  if (debounceId) clearTimeout(debounceId)
  activeIndex.value = -1
  if (!q.trim()) {
    groupResults.value = []
    return
  }
  const currentId = ++requestId
  onCleanup(() => { requestId++ })
  debounceId = setTimeout(async () => {
    groupLoading.value = true
    groupError.value = false
    try {
      const results = await groupsApi.search(q.trim())
      if (currentId === requestId) groupResults.value = results
    } catch {
      if (currentId === requestId) {
        groupError.value = true
        groupResults.value = []
      }
    } finally {
      if (currentId === requestId) groupLoading.value = false
    }
  }, 300)
})

function openCombobox() {
  groupOpen.value = true
}

function closeCombobox() {
  groupOpen.value = false
  groupQuery.value = ''
  activeIndex.value = -1
  groupResults.value = []
}

function selectGroup(group: GroupProfile) {
  wizard.updateConfig({ community_path: group.path })
  closeCombobox()
}

function clearGroup() {
  wizard.updateConfig({ community_path: null })
  nextTick(() => searchInputRef.value?.focus())
}

function onKeydown(e: KeyboardEvent) {
  if (!groupOpen.value || groupResults.value.length === 0) return
  if (e.key === 'ArrowDown') {
    e.preventDefault()
    activeIndex.value = Math.min(activeIndex.value + 1, groupResults.value.length - 1)
  } else if (e.key === 'ArrowUp') {
    e.preventDefault()
    activeIndex.value = Math.max(activeIndex.value - 1, 0)
  } else if (e.key === 'Enter' && activeIndex.value >= 0) {
    e.preventDefault()
    selectGroup(groupResults.value[activeIndex.value])
  } else if (e.key === 'Escape') {
    closeCombobox()
  }
}

function onDocumentClick(e: MouseEvent) {
  if (comboboxRef.value && !comboboxRef.value.contains(e.target as Node)) {
    closeCombobox()
  }
}

watch(groupOpen, (open) => {
  if (open) document.addEventListener('click', onDocumentClick)
  else document.removeEventListener('click', onDocumentClick)
})

onUnmounted(() => {
  if (debounceId) clearTimeout(debounceId)
  document.removeEventListener('click', onDocumentClick)
})
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
      <div ref="comboboxRef" class="fr-input-group">
        <label class="fr-label" for="agent-community">
          Communauté
          <span class="fr-hint-text">
            Sélectionnez le groupe avec lequel partager l'agent. Tapez pour rechercher.
          </span>
        </label>

        <div
          v-if="selectedGroupPath"
          class="fr-mt-1w"
          style="display: flex; align-items: center; gap: 0.5rem"
        >
          <span class="fr-icon-group-line" aria-hidden="true" />
          <span class="fr-text--sm">
            Communauté sélectionnée : <strong>{{ selectedGroupPath }}</strong>
          </span>
          <button
            type="button"
            class="fr-btn fr-btn--tertiary-no-outline fr-btn--sm"
            @click="clearGroup"
          >
            Changer
          </button>
        </div>

        <input
          v-else
          id="agent-community"
          ref="searchInputRef"
          v-model="groupQuery"
          class="fr-input"
          type="text"
          role="combobox"
          :aria-expanded="groupOpen"
          aria-autocomplete="list"
          :placeholder="groupLoading ? 'Recherche…' : 'Rechercher un groupe…'"
          @focus="openCombobox"
          @keydown="onKeydown"
        >

        <div
          v-if="groupOpen && (groupResults.length > 0 || groupLoading || groupError || groupQuery.trim())"
          role="listbox"
          style="border: 1px solid var(--border-default-grey); background: var(--background-default-grey); max-height: 240px; overflow-y: auto; margin-top: 2px; border-radius: 4px"
        >
          <div
            v-if="groupLoading"
            class="fr-p-2w fr-text--sm"
            style="color: var(--text-mention-grey)"
          >
            Recherche en cours…
          </div>
          <div
            v-else-if="groupError"
            class="fr-p-2w fr-text--sm"
            style="color: var(--text-default-error)"
          >
            Impossible de charger les groupes.
          </div>
          <div
            v-else-if="groupQuery.trim() && groupResults.length === 0"
            class="fr-p-2w fr-text--sm"
            style="color: var(--text-mention-grey)"
          >
            Aucun groupe ne correspond à « {{ groupQuery }} »
          </div>
          <button
            v-for="(group, index) in groupResults"
            :key="group.id"
            type="button"
            role="option"
            :aria-selected="index === activeIndex"
            :style="{
              display: 'block',
              width: '100%',
              textAlign: 'left',
              padding: '0.5rem 0.75rem',
              background: index === activeIndex ? 'var(--background-alt-blue-france)' : 'transparent',
              border: 'none',
              cursor: 'pointer',
              fontFamily: 'inherit',
              fontSize: '0.875rem',
            }"
            @click="selectGroup(group)"
            @mouseenter="activeIndex = index"
          >
            <strong>{{ group.name }}</strong>
            <span
              style="margin-left: 0.5rem; color: var(--text-mention-grey); font-size: 0.75rem"
            >
              {{ group.path }}
            </span>
          </button>
        </div>
      </div>
    </div>
  </div>
</template>
