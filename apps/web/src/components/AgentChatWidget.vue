<script setup lang="ts">
import { ref, useId, nextTick, watch } from 'vue'
import { ApiError } from '@/api/client'
import { renderMarkdown } from '@/markdown'
import type { StreamChatCallbacks } from '@/api/client'

interface ChatMessage {
  role: string
  content: string
  pending?: boolean
}

interface ToolStep {
  name: string
  status: 'running' | 'done'
  result?: string
}

const props = defineProps<{
  agentName: string
  greeting?: string
  examples?: string[]
  send: (messages: { role: string; content: string }[]) => Promise<{ reply: string }>
  streamSend?: (
    messages: { role: string; content: string }[],
    callbacks: StreamChatCallbacks,
    signal?: AbortSignal,
  ) => Promise<void>
}>()

const inputId = useId()
const history = ref<ChatMessage[]>([])
const message = ref('')
const busy = ref(false)
const error = ref<string | null>(null)
const toolSteps = ref<ToolStep[]>([])
const abortController = ref<AbortController | null>(null)
const scrollContainer = ref<HTMLElement | null>(null)

const ERROR_LABELS: Record<string, string> = {
  llm_unavailable: 'Le modèle de langage est momentanément indisponible. Réessayez dans un instant.',
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

async function scrollToBottom() {
  await nextTick()
  if (scrollContainer.value) {
    scrollContainer.value.scrollTop = scrollContainer.value.scrollHeight
  }
}

watch(() => history.value.length, scrollToBottom)
watch(() => history.value[history.value.length - 1]?.content, scrollToBottom)

async function sendMessage() {
  const content = message.value.trim()
  if (!content || busy.value) return
  history.value.push({ role: 'user', content })
  busy.value = true
  error.value = null
  await scrollToBottom()

  if (props.streamSend) {
    message.value = ''
    await sendMessageStreaming()
  } else {
    await sendMessageClassic()
  }
}

async function sendMessageStreaming() {
  history.value.push({ role: 'assistant', content: '', pending: true })
  toolSteps.value = []
  abortController.value = new AbortController()

  const callbacks: StreamChatCallbacks = {
    onToken: (token) => {
      const last = history.value[history.value.length - 1]
      if (last && last.role === 'assistant') {
        last.content += token
        last.pending = false
      }
      scrollToBottom()
    },
    onToolCall: (name) => {
      toolSteps.value.push({ name, status: 'running' })
    },
    onToolResult: (name, result) => {
      const step = toolSteps.value.find((s) => s.name === name && s.status === 'running')
      if (step) {
        step.status = 'done'
        step.result = result.slice(0, 200)
      }
    },
    onBlocked: (msg) => {
      const last = history.value[history.value.length - 1]
      if (last && last.role === 'assistant') {
        last.content = msg
        last.pending = false
      }
    },
    onDone: () => {
      busy.value = false
      abortController.value = null
      const last = history.value[history.value.length - 1]
      if (last) last.pending = false
    },
    onError: (msg) => {
      error.value = msg || "Échec de l'envoi du message."
      history.value.pop()
      busy.value = false
      abortController.value = null
    },
  }

  try {
    await props.streamSend!(history.value.slice(0, -1), callbacks, abortController.value.signal)
  } catch (err) {
    if (err instanceof DOMException && err.name === 'AbortError') {
      // user cancelled — keep partial response
    } else {
      error.value = describeError(err)
    }
  } finally {
    busy.value = false
    abortController.value = null
    const last = history.value[history.value.length - 1]
    if (last) last.pending = false
  }
}

async function sendMessageClassic() {
  try {
    const res = await props.send(history.value)
    history.value.push({ role: 'assistant', content: res.reply })
    message.value = ''
  } catch (err) {
    history.value.pop()
    error.value = describeError(err)
  } finally {
    busy.value = false
  }
}

function stopGeneration() {
  abortController.value?.abort()
  busy.value = false
}

function useExample(example: string) {
  message.value = example
}

function reset() {
  if (busy.value) stopGeneration()
  history.value = []
  toolSteps.value = []
  error.value = null
}
</script>

<template>
  <div>
    <p v-if="greeting && history.length === 0" class="fr-hint-text fr-mb-2w">{{ greeting }}</p>

    <div v-if="examples && examples.length > 0 && history.length === 0" class="fr-mb-2w">
      <button
        v-for="ex in examples.slice(0, 4)"
        :key="ex"
        class="fr-tag fr-tag--sm fr-mr-1w fr-mb-1w"
        type="button"
        :disabled="busy"
        @click="useExample(ex)"
      >
        {{ ex }}
      </button>
    </div>

    <div
      v-if="history.length || busy"
      ref="scrollContainer"
      class="fr-mb-2w"
      style="display: flex; flex-direction: column; gap: 0.75rem; max-height: 500px; overflow-y: auto"
      role="log"
      aria-live="polite"
    >
      <template v-for="(m, i) in history" :key="i">
        <div v-if="m.role === 'user'" class="fr-callout fr-mb-0 fr-py-1w fr-px-2w">
          <p class="fr-mb-0" style="font-weight: 600">Vous : {{ m.content }}</p>
        </div>
        <div v-else class="reponse-agent fr-p-2w" style="background: var(--background-alt-grey); border-radius: 4px">
          <p class="fr-mb-0 fr-text--bold">{{ agentName }}</p>
          <div v-if="m.content" v-html="renderMarkdown(m.content)" />
          <span v-if="m.pending && !m.content" class="fr-text--sm" style="color: var(--text-mention-grey)">
            {{ agentName }} écrit...
          </span>
        </div>
      </template>

      <div v-for="(step, i) in toolSteps" :key="`tool-${i}`" class="fr-text--sm" style="color: var(--text-mention-grey)">
        <span v-if="step.status === 'running'">🔧 {{ step.name }} en cours...</span>
        <span v-else>✅ {{ step.name }} terminé</span>
      </div>
    </div>

    <div v-if="error" class="fr-alert fr-alert--error fr-alert--sm fr-mb-2w">
      <p>{{ error }}</p>
    </div>

    <div class="fr-input-group fr-mb-0">
      <label class="fr-label" :for="inputId">Votre message</label>
      <div style="display: flex; gap: 0.5rem; align-items: flex-end">
        <textarea
          :id="inputId"
          v-model="message"
          class="fr-input"
          rows="1"
          :disabled="busy"
          style="resize: vertical; min-height: 40px"
          @keydown.enter.exact.prevent="sendMessage"
        />
        <button v-if="busy && abortController" class="fr-btn fr-btn--tertiary" type="button" @click="stopGeneration">
          Arrêter
        </button>
        <button v-else class="fr-btn" :disabled="busy || !message.trim()" @click="sendMessage">
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
.reponse-agent :deep(pre) {
  background: var(--background-contrast-grey);
  padding: 0.5rem;
  border-radius: 4px;
  overflow-x: auto;
}
.reponse-agent :deep(code) {
  font-family: monospace;
}
</style>
