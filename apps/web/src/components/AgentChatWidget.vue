<script setup lang="ts">
import { ref, useId } from 'vue'
import { ApiError } from '@/api/client'
import { renderMarkdown } from '@/markdown'

const props = defineProps<{
  agentName: string
  greeting?: string
  send: (messages: { role: string; content: string }[]) => Promise<{ reply: string }>
}>()

const inputId = useId()
const history = ref<{ role: string; content: string }[]>([])
const message = ref('')
const busy = ref(false)
const error = ref<string | null>(null)

const ERROR_LABELS: Record<string, string> = {
  llm_unavailable: "Le modèle de langage est momentanément indisponible. Réessayez dans un instant.",
  forbidden: "Vous n'avez pas le droit de discuter avec cet agent.",
  not_found: "Cet agent est introuvable ou n'est plus disponible.",
}

function describeError(err: unknown): string {
  if (err instanceof ApiError) {
    try {
      const detail = (JSON.parse(err.message) as { detail?: string }).detail
      if (detail) return ERROR_LABELS[detail] ?? detail
    } catch {
      // body wasn't JSON — fall through to the generic message below
    }
  }
  return "Échec de l'envoi du message. L'agent est peut-être indisponible."
}

async function sendMessage() {
  const content = message.value.trim()
  if (!content || busy.value) return
  history.value.push({ role: 'user', content })
  busy.value = true
  error.value = null
  try {
    const res = await props.send(history.value)
    history.value.push({ role: 'assistant', content: res.reply })
    message.value = ''
  } catch (err) {
    // Roll back the optimistic message so the user can retry without a dangling turn.
    history.value.pop()
    error.value = describeError(err)
  } finally {
    busy.value = false
  }
}

function reset() {
  history.value = []
  error.value = null
}
</script>

<template>
  <div>
    <p v-if="greeting && history.length === 0" class="fr-hint-text">{{ greeting }}</p>

    <div
      v-if="history.length"
      class="fr-mb-2w"
      style="display: flex; flex-direction: column; gap: 0.5rem; max-height: 320px; overflow-y: auto"
    >
      <template v-for="(m, i) in history" :key="i">
        <p v-if="m.role === 'user'" class="fr-mb-0" style="font-weight: 600">
          Vous : {{ m.content }}
        </p>
        <!-- Réponse de l'agent : Markdown rendu puis assaini (src/markdown.ts). -->
        <div v-else class="reponse-agent">
          <p class="fr-mb-0 fr-text--bold">{{ agentName }} :</p>
          <!-- eslint-disable-next-line vue/no-v-html -->
          <div v-html="renderMarkdown(m.content)" />
        </div>
      </template>
      <p v-if="busy" class="fr-mb-0 fr-text--sm" style="color: var(--text-mention-grey)">
        {{ agentName }} écrit...
      </p>
    </div>

    <div v-if="error" class="fr-alert fr-alert--error fr-alert--sm fr-mb-2w">
      <p>{{ error }}</p>
    </div>

    <div class="fr-input-group fr-mb-0">
      <label class="fr-label" :for="inputId">Votre message</label>
      <div style="display: flex; gap: 0.5rem">
        <input
          :id="inputId"
          v-model="message"
          class="fr-input"
          type="text"
          :disabled="busy"
          @keyup.enter="sendMessage"
        >
        <button class="fr-btn" :disabled="busy || !message.trim()" @click="sendMessage">
          Envoyer
        </button>
      </div>
    </div>
    <button
      v-if="history.length"
      class="fr-btn fr-btn--tertiary-no-outline fr-btn--sm fr-mt-1w"
      type="button"
      @click="reset"
    >
      Réinitialiser la conversation
    </button>
  </div>
</template>

<style scoped>
/* Marges du DSFR trop généreuses dans une bulle de discussion. */
.reponse-agent :deep(p),
.reponse-agent :deep(ul),
.reponse-agent :deep(ol),
.reponse-agent :deep(pre),
.reponse-agent :deep(blockquote) {
  margin: 0 0 0.5rem;
}
.reponse-agent :deep(ul),
.reponse-agent :deep(ol) {
  padding-left: 1.5rem;
}
</style>
