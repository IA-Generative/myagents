<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { toolsApi } from '@/api/tools'
import { knowledgeApi } from '@/api/knowledge'
import { ApiError } from '@/api/client'
import { useWizardStore } from '@/stores/wizard'
import type { KnowledgeBase, ToolProfile } from '@/types/agent'

const wizard = useWizardStore()

const tools = ref<ToolProfile[]>([])
const knowledgeBases = ref<KnowledgeBase[]>([])
const newKbName = ref('')
const uploadingKbId = ref<string | null>(null)
const error = ref<string | null>(null)

function apiErrorMessage(err: unknown, fallback: string): string {
  if (err instanceof ApiError) {
    try {
      const parsed = JSON.parse(err.message)
      return parsed.detail ?? parsed.message ?? fallback
    } catch {
      return err.message || fallback
    }
  }
  return fallback
}

onMounted(async () => {
  tools.value = await toolsApi.list()
  knowledgeBases.value = await knowledgeApi.list()
})

function toggleTool(toolId: string, checked: boolean) {
  const current = wizard.draft.config.tool_ids
  wizard.updateConfig({
    tool_ids: checked ? [...current, toolId] : current.filter((id) => id !== toolId),
  })
}

function toggleKnowledgeBase(kbId: string, checked: boolean) {
  const current = wizard.draft.config.knowledge_ids
  wizard.updateConfig({
    knowledge_ids: checked ? [...current, kbId] : current.filter((id) => id !== kbId),
  })
}

async function createKnowledgeBase() {
  const name = newKbName.value.trim()
  if (!name) return
  error.value = null
  try {
    const kb = await knowledgeApi.create(name)
    knowledgeBases.value = [kb, ...knowledgeBases.value]
    newKbName.value = ''
  } catch (err) {
    error.value = apiErrorMessage(err, 'Échec de la création de la base de connaissances.')
  }
}

async function removeKnowledgeBase(kbId: string) {
  error.value = null
  try {
    await knowledgeApi.remove(kbId)
    knowledgeBases.value = knowledgeBases.value.filter((kb) => kb.id !== kbId)
    toggleKnowledgeBase(kbId, false)
  } catch (err) {
    error.value = apiErrorMessage(err, 'Échec de la suppression de la base de connaissances.')
  }
}

async function uploadDocument(kb: KnowledgeBase, event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  uploadingKbId.value = kb.id
  error.value = null
  try {
    const doc = await knowledgeApi.uploadDocument(kb.id, file)
    kb.documents = [...kb.documents, doc]
  } catch (err) {
    error.value = apiErrorMessage(err, "Échec de l'import du document.")
  } finally {
    uploadingKbId.value = null
    input.value = ''
  }
}
</script>

<template>
  <div class="fr-grid-row fr-grid-row--gutters">
    <div v-if="error" class="fr-col-12">
      <div class="fr-alert fr-alert--error fr-alert--sm">
        <p>{{ error }}</p>
      </div>
    </div>

    <div class="fr-col-12">
      <h3>Outils</h3>
      <p class="fr-hint-text">
        Les outils permettent à l'agent d'effectuer des actions supplémentaires pendant la
        conversation (ex : connaître la date du jour).
      </p>
      <div v-for="t in tools" :key="t.id" class="fr-checkbox-group">
        <input
          :id="`tool-${t.id}`"
          type="checkbox"
          :checked="wizard.draft.config.tool_ids.includes(t.id)"
          @change="toggleTool(t.id, ($event.target as HTMLInputElement).checked)"
        >
        <label class="fr-label" :for="`tool-${t.id}`">
          {{ t.label }}
          <span class="fr-hint-text">{{ t.description }}</span>
        </label>
      </div>
    </div>

    <div class="fr-col-12">
      <hr class="fr-mt-3w">
      <h3>Bases de connaissances</h3>
      <p class="fr-hint-text">
        Attachez une ou plusieurs bases de connaissances : l'agent pourra y rechercher des
        informations pour répondre (fichiers texte ou Markdown).
      </p>

      <div class="fr-input-group">
        <label class="fr-label" for="new-kb-name">Nouvelle base de connaissances</label>
        <div style="display: flex; gap: 0.5rem">
          <input
            id="new-kb-name"
            v-model="newKbName"
            class="fr-input"
            type="text"
            placeholder="Ex : Procédures RH"
            @keyup.enter="createKnowledgeBase"
          >
          <button class="fr-btn fr-btn--secondary" type="button" @click="createKnowledgeBase">
            Créer
          </button>
        </div>
      </div>

      <ul class="fr-mt-2w" style="list-style: none; padding: 0">
        <li v-for="kb in knowledgeBases" :key="kb.id" class="fr-mb-2w">
          <div class="fr-checkbox-group">
            <input
              :id="`kb-${kb.id}`"
              type="checkbox"
              :checked="wizard.draft.config.knowledge_ids.includes(kb.id)"
              @change="toggleKnowledgeBase(kb.id, ($event.target as HTMLInputElement).checked)"
            >
            <label class="fr-label" :for="`kb-${kb.id}`">
              {{ kb.name }}
              <span class="fr-hint-text">
                {{ kb.documents.length }} document(s) :
                {{ kb.documents.map((d) => d.filename).join(', ') || 'aucun' }}
              </span>
            </label>
          </div>
          <div style="display: flex; align-items: center; gap: 1rem" class="fr-mt-1w">
            <label class="fr-label fr-text--sm" :for="`upload-${kb.id}`">
              Ajouter un document (.txt, .md)
            </label>
            <input
              :id="`upload-${kb.id}`"
              type="file"
              accept=".txt,.md"
              :disabled="uploadingKbId === kb.id"
              @change="uploadDocument(kb, $event)"
            >
            <button
              class="fr-btn fr-btn--tertiary-no-outline fr-btn--sm"
              type="button"
              @click="removeKnowledgeBase(kb.id)"
            >
              Supprimer la base
            </button>
          </div>
        </li>
      </ul>
    </div>
  </div>
</template>
