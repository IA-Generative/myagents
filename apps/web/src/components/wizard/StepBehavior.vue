<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { modelsApi } from '@/api/models'
import { promptApi } from '@/api/prompt'
import { ApiError } from '@/api/client'
import { useWizardStore } from '@/stores/wizard'
import type { ModelProfile } from '@/types/agent'

const wizard = useWizardStore()
const models = ref<ModelProfile[]>([])
const modelsLoading = ref(false)
const busy = ref<null | 'assist' | 'optimize' | 'starters' | 'validate'>(null)
const error = ref<string | null>(null)

const selectedModel = () => models.value.find((m) => m.id === wizard.draft.config.model_id)

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

async function loadModels() {
  modelsLoading.value = true
  try {
    models.value = await modelsApi.list()
    if (!wizard.draft.config.model_id && models.value.length > 0) {
      wizard.updateConfig({ model_id: models.value[0].id })
    }
  } finally {
    modelsLoading.value = false
  }
}

onMounted(loadModels)

async function assist() {
  busy.value = 'assist'
  error.value = null
  try {
    const res = await promptApi.assist(wizard.draft.config.system_prompt)
    wizard.updateConfig({ system_prompt: res.prompt })
  } catch (err) {
    error.value = apiErrorMessage(err, "Échec de l'assistance à la rédaction.")
  } finally {
    busy.value = null
  }
}

async function optimize() {
  busy.value = 'optimize'
  error.value = null
  try {
    const res = await promptApi.optimize(wizard.draft.config.system_prompt)
    wizard.updateConfig({ system_prompt: res.prompt })
  } catch (err) {
    error.value = apiErrorMessage(err, "Échec de l'optimisation du prompt.")
  } finally {
    busy.value = null
  }
}

async function generateStarters() {
  if (wizard.draft.config.system_prompt.trim().length < 20) {
    error.value = 'Le prompt système doit faire au moins 20 caractères pour générer une amorce.'
    return
  }
  busy.value = 'starters'
  error.value = null
  try {
    const res = await promptApi.suggestStarters(wizard.draft.config.system_prompt, 4)
    wizard.updateConfig({ greeting: res.greeting, examples: res.examples })
  } catch (err) {
    error.value = apiErrorMessage(err, "Échec de la génération de l'amorce et des exemples.")
  } finally {
    busy.value = null
  }
}

// Validation OBLIGATOIRE des instructions système. Tant qu'elle n'est pas
// effectuée, la navigation « Suivant » reste bloquée (cf. AgentWizardPage.vue).
async function validate() {
  if (!wizard.draft.config.system_prompt.trim()) {
    error.value = 'Saisissez des instructions système avant de les valider.'
    return
  }
  busy.value = 'validate'
  error.value = null
  try {
    await promptApi.validate(wizard.draft.config.system_prompt)
    wizard.setPromptValidated(true)
  } catch (err) {
    wizard.setPromptValidated(false)
    error.value = apiErrorMessage(err, 'La validation des instructions système a échoué.')
  } finally {
    busy.value = null
  }
}

function updateExample(index: number, value: string) {
  const examples = [...wizard.draft.config.examples]
  examples[index] = value
  wizard.updateConfig({ examples })
}

function addExample() {
  if (wizard.draft.config.examples.length >= 6) return
  wizard.updateConfig({ examples: [...wizard.draft.config.examples, ''] })
}

function removeExample(index: number) {
  wizard.updateConfig({ examples: wizard.draft.config.examples.filter((_, i) => i !== index) })
}
</script>

<template>
  <div class="fr-grid-row fr-grid-row--gutters">
    <div class="fr-col-12">
      <div class="fr-input-group">
        <label class="fr-label" for="system-prompt">
          Instructions système
          <span class="fr-hint-text">
            Décris le rôle, le public, le ton et les contraintes de l'agent. Si tu hésites,
            clique sur « Aide-moi à écrire ». 10 000 caractères max.
          </span>
        </label>
        <textarea
          id="system-prompt"
          v-model="wizard.draft.config.system_prompt"
          class="fr-input"
          rows="10"
          maxlength="10000"
          placeholder="Ex : Tu es un assistant spécialisé dans la rédaction de notes juridiques..."
          @input="wizard.setPromptValidated(false)"
        />
      </div>
      <div class="fr-btns-group fr-btns-group--inline">
        <button
          type="button"
          class="fr-btn fr-btn--secondary"
          :disabled="busy !== null"
          @click="assist"
        >
          {{ busy === 'assist' ? 'Génération…' : 'Aide-moi à écrire' }}
        </button>
        <button
          type="button"
          class="fr-btn fr-btn--secondary"
          :disabled="busy !== null || !wizard.draft.config.system_prompt"
          @click="optimize"
        >
          {{ busy === 'optimize' ? 'Optimisation…' : 'Optimiser mon prompt' }}
        </button>
      </div>

      <div class="fr-mt-2w" style="display: flex; align-items: center; gap: 1rem; flex-wrap: wrap">
        <button
          type="button"
          :class="
            wizard.promptValidated
              ? 'fr-btn fr-icon-checkbox-circle-line fr-btn--icon-left'
              : 'fr-btn fr-btn--secondary fr-icon-shield-line fr-btn--icon-left'
          "
          :disabled="busy !== null || !wizard.draft.config.system_prompt || wizard.promptValidated"
          @click="validate"
        >
          {{
            busy === 'validate'
              ? 'Validation…'
              : wizard.promptValidated
                ? 'Instructions validées ✓'
                : 'Valider les instructions système'
          }}
        </button>
        <span class="fr-hint-text" style="margin: 0">
          {{
            wizard.promptValidated
              ? "Vous pouvez passer à l'étape suivante."
              : "La validation des instructions système est obligatoire avant de passer à l'étape suivante."
          }}
        </span>
      </div>

      <div v-if="error" class="fr-alert fr-alert--error fr-alert--sm fr-mt-2w">
        <p>{{ error }}</p>
      </div>
    </div>

    <div class="fr-col-12">
      <div class="fr-input-group">
        <label class="fr-label" for="greeting">
          Amorce de conversation
          <span class="fr-hint-text">
            Message d'accueil affiché à l'utilisateur au lancement de l'agent.
          </span>
        </label>
        <textarea
          id="greeting"
          v-model="wizard.draft.config.greeting"
          class="fr-input"
          rows="3"
          maxlength="500"
          placeholder="Ex : Bonjour, je suis votre assistant..."
        />
      </div>
      <button
        type="button"
        class="fr-btn fr-btn--secondary fr-icon-magic-wand-line fr-btn--icon-left"
        :disabled="busy !== null || wizard.draft.config.system_prompt.trim().length < 20"
        @click="generateStarters"
      >
        {{ busy === 'starters' ? 'Génération…' : 'Générer amorce + exemples depuis le prompt' }}
      </button>
    </div>

    <div class="fr-col-12">
      <fieldset class="fr-fieldset">
        <legend class="fr-fieldset__legend">
          Exemples de prompts (cliquables)
          <span class="fr-hint-text">
            Jusqu'à 6 suggestions proposées à l'utilisateur final.
          </span>
        </legend>
        <div class="fr-fieldset__content">
          <p v-if="wizard.draft.config.examples.length === 0" class="fr-text--sm">
            Aucun exemple pour l'instant.
          </p>
          <div
            v-for="(example, i) in wizard.draft.config.examples"
            :key="i"
            class="fr-mb-2w"
            style="display: flex; gap: 0.5rem; align-items: flex-start"
          >
            <input
              type="text"
              class="fr-input"
              maxlength="200"
              :value="example"
              style="flex: 1"
              @input="updateExample(i, ($event.target as HTMLInputElement).value)"
            >
            <button
              type="button"
              class="fr-btn fr-btn--tertiary fr-btn--sm fr-icon-delete-line"
              title="Retirer cet exemple"
              @click="removeExample(i)"
            >
              Retirer
            </button>
          </div>
          <button
            v-if="wizard.draft.config.examples.length < 6"
            type="button"
            class="fr-btn fr-btn--tertiary-no-outline fr-btn--icon-left fr-icon-add-line"
            @click="addExample"
          >
            Ajouter un exemple
          </button>
        </div>
      </fieldset>
    </div>

    <div class="fr-col-12">
      <div class="fr-select-group">
        <label class="fr-label" for="model">
          Modèle de base
          <span class="fr-hint-text">Choisissez le moteur IA.</span>
        </label>
        <select id="model" v-model="wizard.draft.config.model_id" class="fr-select">
          <option v-for="m in models" :key="m.id" :value="m.id">{{ m.label }}</option>
        </select>
        <p v-if="modelsLoading" class="fr-hint-text">Chargement des modèles...</p>
      </div>
      <div v-if="selectedModel()" class="fr-callout fr-mt-2w">
        <h3 class="fr-callout__title" style="display: flex; align-items: center; gap: 0.5rem">
          {{ selectedModel()?.label }}
          <span class="fr-badge fr-badge--sm">{{ selectedModel()?.tier }}</span>
        </h3>
        <p v-if="selectedModel()?.short_pitch" class="fr-callout__text">
          {{ selectedModel()?.short_pitch }}
        </p>
      </div>
    </div>

    <div class="fr-col-12 fr-col-md-6">
      <label class="fr-label" for="temperature">
        Température (Précis ↔ Créatif) — {{ wizard.draft.config.temperature.toFixed(1) }}
      </label>
      <input
        id="temperature"
        v-model.number="wizard.draft.config.temperature"
        class="fr-range"
        type="range"
        min="0"
        max="1"
        step="0.1"
      >
    </div>
  </div>
</template>
