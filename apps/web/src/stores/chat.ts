import { defineStore } from 'pinia'
import { ref } from 'vue'
import { agentsApi } from '@/api/agents'
import type { Conversation, ConversationMessage } from '@/types/agent'

interface ChatMessage {
  role: string
  content: string
  pending?: boolean
}

export const useChatStore = defineStore('chat', () => {
  const conversations = ref<Conversation[]>([])
  const activeConversationId = ref<string | null>(null)
  const messages = ref<ChatMessage[]>([])
  const streaming = ref(false)
  const toolActivity = ref<{ name: string; status: 'running' | 'done'; result?: string }[]>([])

  async function loadConversations(agentId?: string) {
    conversations.value = await agentsApi.conversations(agentId)
  }

  async function loadConversation(convId: string) {
    activeConversationId.value = convId
    const msgs = await agentsApi.conversationMessages(convId)
    messages.value = msgs.map((m: ConversationMessage) => ({
      role: m.role,
      content: m.content,
    }))
  }

  function startNewConversation() {
    activeConversationId.value = null
    messages.value = []
    toolActivity.value = []
  }

  function addUserMessage(content: string) {
    messages.value.push({ role: 'user', content })
  }

  function startStreaming() {
    streaming.value = true
    toolActivity.value = []
    messages.value.push({ role: 'assistant', content: '', pending: true })
  }

  function appendToken(content: string) {
    const last = messages.value[messages.value.length - 1]
    if (last && last.role === 'assistant') {
      last.content += content
    }
  }

  function addToolCall(name: string) {
    toolActivity.value.push({ name, status: 'running' })
  }

  function completeToolCall(name: string, result: string) {
    const tool = toolActivity.value.find((t) => t.name === name && t.status === 'running')
    if (tool) {
      tool.status = 'done'
      tool.result = result
    }
  }

  function finishStreaming(conversationId?: string) {
    streaming.value = false
    const last = messages.value[messages.value.length - 1]
    if (last) last.pending = false
    if (conversationId) activeConversationId.value = conversationId
  }

  function blockStreaming(message: string) {
    streaming.value = false
    const last = messages.value[messages.value.length - 1]
    if (last && last.role === 'assistant' && last.pending) {
      last.content = message
      last.pending = false
    }
  }

  function reset() {
    messages.value = []
    toolActivity.value = []
    activeConversationId.value = null
    streaming.value = false
  }

  return {
    conversations,
    activeConversationId,
    messages,
    streaming,
    toolActivity,
    loadConversations,
    loadConversation,
    startNewConversation,
    addUserMessage,
    startStreaming,
    appendToken,
    addToolCall,
    completeToolCall,
    finishStreaming,
    blockStreaming,
    reset,
  }
})
