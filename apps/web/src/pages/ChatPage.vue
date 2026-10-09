<script setup lang="ts">
import { ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import AgentChatWidget from '@/components/AgentChatWidget.vue'
import { agentsApi } from '@/api/agents'
import type { AgentDetail, Conversation } from '@/types/agent'
import type { StreamChatCallbacks } from '@/api/client'

const route = useRoute()
const agent = ref<AgentDetail | null>(null)
const conversations = ref<Conversation[]>([])
const selectedConversationId = ref<string | null>(null)
const loading = ref(true)
const error = ref<string | null>(null)

async function loadAgent(agentId: string) {
  loading.value = true
  error.value = null
  try {
    agent.value = await agentsApi.get(agentId)
    await loadConversations(agentId)
  } catch {
    error.value = 'Agent introuvable.'
  } finally {
    loading.value = false
  }
}

async function loadConversations(agentId: string) {
  try {
    conversations.value = await agentsApi.conversations(agentId)
  } catch {
    conversations.value = []
  }
}

async function selectConversation(convId: string) {
  selectedConversationId.value = convId
  await loadConversationMessages(convId)
}

async function loadConversationMessages(convId: string) {
  try {
    const msgs = await agentsApi.conversationMessages(convId)
    // Remplir le widget via un key change pour forcer le reset
    widgetKey.value++
    selectedConversationMessages.value = msgs.map((m) => ({
      role: m.role,
      content: m.content,
    }))
  } catch {
    // ignore — l'utilisateur repartira d'une conversation vide
  }
}

const selectedConversationMessages = ref<{ role: string; content: string }[]>([])
const widgetKey = ref(0)

async function sendMessage(
  messages: { role: string; content: string }[],
): Promise<{ reply: string }> {
  if (!agent.value) throw new Error('No agent')
  return agentsApi.chat(agent.value.id, messages, selectedConversationId.value ?? undefined)
}

async function streamSend(
  messages: { role: string; content: string }[],
  callbacks: StreamChatCallbacks,
  signal?: AbortSignal,
): Promise<void> {
  if (!agent.value) throw new Error('No agent')
  await agentsApi.chatStream(
    agent.value.id,
    messages,
    callbacks,
    selectedConversationId.value ?? undefined,
    signal,
  )
}

const agentId = route.query.agent as string | undefined

watch(
  () => agentId,
  (id) => {
    if (id) loadAgent(id)
  },
  { immediate: true },
)
</script>

<template>
  <div class="fr-container fr-py-4w">
    <div v-if="loading" class="fr-text--sm">Chargement…</div>
    <div v-else-if="error" class="fr-alert fr-alert--error">
      <p>{{ error }}</p>
    </div>
    <div v-else-if="agent">
      <h1 class="fr-h2 fr-mb-2w">{{ agent.config.name }}</h1>
      <p v-if="conversations.length > 0" class="fr-text--sm fr-mb-2w">
        <button
          v-for="conv in conversations.slice(0, 5)"
          :key="conv.id"
          class="fr-tag fr-tag--sm fr-mr-1w"
          type="button"
          :aria-pressed="selectedConversationId === conv.id"
          @click="selectConversation(conv.id)"
        >
          {{ conv.title || 'Conversation' }}
        </button>
      </p>
      <AgentChatWidget
        :key="widgetKey"
        :agent-name="agent.config.name"
        :greeting="agent.config.greeting"
        :examples="agent.config.examples"
        :send="sendMessage"
        :stream-send="streamSend"
      />
    </div>
    <div v-else class="fr-text--sm">
      Sélectionnez un agent depuis la liste pour démarrer une conversation.
    </div>
  </div>
</template>
