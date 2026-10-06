<script setup lang="ts">
import { nextTick, ref } from 'vue'
import { useRouter } from 'vue-router'
import { promptApi } from '@/api/prompt'
import type { OnboardingAgentConfig, OnboardingMessage } from '@/types/agent'

const router = useRouter()
const open = ref(false)
const started = ref(false)
const messages = ref<OnboardingMessage[]>([])
const input = ref('')
const busy = ref(false)
const error = ref<string | null>(null)
const agentConfig = ref<OnboardingAgentConfig | null>(null)
const messagesContainer = ref<HTMLElement | null>(null)

const ONBOARDING_STORAGE_KEY = 'onboarding_agent_config'

async function scrollToBottom() {
  await nextTick()
  const el = messagesContainer.value
  if (el) el.scrollTop = el.scrollHeight
}

async function startChat() {
  open.value = true
  if (started.value) return
  started.value = true
  busy.value = true
  try {
    const greeting: OnboardingMessage = {
      role: 'user',
      content: 'Bonjour, je souhaite créer un agent.',
    }
    const res = await promptApi.onboardingChat([greeting])
    messages.value = [greeting, { role: 'assistant', content: res.message }]
    if (res.agent_config?.ready) agentConfig.value = res.agent_config
    await scrollToBottom()
  } catch {
    error.value = "Impossible de démarrer l'assistant pour le moment."
  } finally {
    busy.value = false
  }
}

async function send() {
  const text = input.value.trim()
  if (!text || busy.value) return
  messages.value.push({ role: 'user', content: text })
  input.value = ''
  busy.value = true
  error.value = null
  await scrollToBottom()
  try {
    const res = await promptApi.onboardingChat(messages.value)
    messages.value.push({ role: 'assistant', content: res.message })
    if (res.agent_config?.ready) agentConfig.value = res.agent_config
    await scrollToBottom()
  } catch {
    error.value = 'Une erreur est survenue. Réessayez.'
  } finally {
    busy.value = false
  }
}

async function retry() {
  // Retire le dernier message utilisateur (celui qui a échoué) et le renvoie.
  const last = messages.value[messages.value.length - 1]
  if (last?.role !== 'user') return
  const text = last.content
  messages.value.pop()
  input.value = text
  await send()
}

function createAgent() {
  if (!agentConfig.value) return
  // La config peut contenir un system_prompt jusqu'à 20 Ko : trop long pour une
  // query string d'URL. On passe par sessionStorage, lu puis effacé par le wizard.
  sessionStorage.setItem(
    ONBOARDING_STORAGE_KEY,
    JSON.stringify(agentConfig.value),
  )
  router.push({ name: 'agent-new', query: { onboarding: '1' } })
}
</script>

<template>
  <button
    v-if="!open"
    type="button"
    class="fr-btn fr-icon-chat-3-line fr-btn--icon-left"
    style="position: fixed; bottom: 1.5rem; right: 1.5rem; z-index: 100"
    @click="startChat"
  >
    Besoin d'aide pour créer un agent ?
  </button>

  <div
    v-else
    style="
      position: fixed;
      bottom: 1.5rem;
      right: 1.5rem;
      width: 360px;
      max-height: 70vh;
      display: flex;
      flex-direction: column;
      background: var(--background-default-grey);
      border: 1px solid var(--border-default-grey);
      border-radius: 8px;
      box-shadow: 0 4px 16px rgba(0, 0, 0, 0.2);
      z-index: 100;
    "
  >
    <div
      style="
        padding: 0.75rem 1rem;
        border-bottom: 1px solid var(--border-default-grey);
        display: flex;
        justify-content: space-between;
        align-items: center;
      "
    >
      <strong class="fr-text--sm">Assistant de création d'agent</strong>
      <button type="button" class="fr-btn fr-btn--tertiary-no-outline fr-btn--sm fr-icon-close-line" @click="open = false">
        Fermer
      </button>
    </div>

    <div
      ref="messagesContainer"
      style="flex: 1; overflow-y: auto; padding: 0.75rem"
      aria-live="polite"
      aria-atomic="false"
    >
      <div
        v-for="(m, i) in messages"
        :key="i"
        class="fr-mb-2w"
        :style="{ textAlign: m.role === 'user' ? 'right' : 'left' }"
      >
        <span
          style="display: inline-block; padding: 0.5rem 0.75rem; border-radius: 12px; background: var(--background-contrast-grey)"
        >
          {{ m.content }}
        </span>
      </div>
      <div v-if="busy" class="fr-mb-2w" style="text-align: left">
        <span
          class="fr-text--sm"
          style="display: inline-block; padding: 0.5rem 0.75rem; border-radius: 12px; background: var(--background-contrast-grey); color: var(--text-mention-grey)"
        >
          L'assistant rédige sa réponse…
        </span>
      </div>
      <p v-if="error" class="fr-text--sm" style="color: var(--text-default-error)">
        {{ error }}
        <button
          type="button"
          class="fr-btn fr-btn--tertiary-no-outline fr-btn--sm fr-mt-1v"
          @click="retry"
        >
          Réessayer
        </button>
      </p>
    </div>

    <div v-if="agentConfig" style="padding: 0.75rem 1rem; border-top: 1px solid var(--border-default-grey)">
      <p class="fr-text--sm fr-mb-1w">
        <strong>{{ agentConfig.name }}</strong> est prêt à être créé !
      </p>
      <button type="button" class="fr-btn fr-btn--sm" @click="createAgent">Créer cet agent</button>
    </div>

    <div style="padding: 0.75rem; border-top: 1px solid var(--border-default-grey); display: flex; gap: 0.5rem">
      <input
        v-model="input"
        class="fr-input"
        type="text"
        placeholder="Votre réponse..."
        :disabled="busy"
        @keyup.enter="send"
      >
      <button type="button" class="fr-btn fr-btn--sm" :disabled="busy" @click="send">Envoyer</button>
    </div>
  </div>
</template>
