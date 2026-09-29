<script setup lang="ts">
import { ref } from 'vue'
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
  try {
    const res = await promptApi.onboardingChat(messages.value)
    messages.value.push({ role: 'assistant', content: res.message })
    if (res.agent_config?.ready) agentConfig.value = res.agent_config
  } catch {
    error.value = 'Une erreur est survenue. Réessayez.'
  } finally {
    busy.value = false
  }
}

function createAgent() {
  if (!agentConfig.value) return
  const encoded = encodeURIComponent(JSON.stringify(agentConfig.value))
  router.push({ name: 'agent-new', query: { onboarding: encoded } })
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

    <div style="flex: 1; overflow-y: auto; padding: 0.75rem">
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
      <p v-if="error" class="fr-text--sm" style="color: var(--text-default-error)">{{ error }}</p>
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
