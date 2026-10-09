import { flushPromises, mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'
import AgentChatWidget from './AgentChatWidget.vue'
import { ApiError } from '@/api/client'

describe('AgentChatWidget', () => {
  it('sends a message and displays the reply', async () => {
    const calls: { role: string; content: string }[][] = []
    const send = vi.fn(async (messages: { role: string; content: string }[]) => {
      calls.push(messages.map((m) => ({ role: m.role, content: m.content })))
      return { reply: 'Bonjour !' }
    })
    const wrapper = mount(AgentChatWidget, {
      props: { agentName: 'Mon agent', send },
    })

    await wrapper.find('textarea').setValue('Salut')
    await wrapper.find('button').trigger('click')
    await flushPromises()

    expect(calls[0]).toEqual([{ role: 'user', content: 'Salut' }])
    expect(wrapper.text()).toContain('Bonjour !')
  })

  it('sends the full running history on the second message', async () => {
    const calls: { role: string; content: string }[][] = []
    const send = vi.fn(async (messages: { role: string; content: string }[]) => {
      calls.push(messages.map((m) => ({ role: m.role, content: m.content })))
      return { reply: `reponse-${calls.length}` }
    })
    const wrapper = mount(AgentChatWidget, {
      props: { agentName: 'Mon agent', send },
    })

    await wrapper.find('textarea').setValue('Premier message')
    await wrapper.find('button').trigger('click')
    await flushPromises()

    await wrapper.find('textarea').setValue('Deuxieme message')
    await wrapper.find('button').trigger('click')
    await flushPromises()

    expect(calls[1]).toEqual([
      { role: 'user', content: 'Premier message' },
      { role: 'assistant', content: 'reponse-1' },
      { role: 'user', content: 'Deuxieme message' },
    ])
  })

  it('shows an error message and lets the user retry on failure', async () => {
    const send = vi.fn().mockRejectedValue(new Error('boom'))
    const wrapper = mount(AgentChatWidget, {
      props: { agentName: 'Mon agent', send },
    })

    await wrapper.find('textarea').setValue('Salut')
    await wrapper.find('button').trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('Échec de l')
    // The failed turn is rolled back so it doesn't linger unanswered in the history.
    expect(wrapper.text()).not.toContain('Vous : Salut')
    expect((wrapper.find('textarea').element as HTMLTextAreaElement).value).toBe('Salut')
  })

  it('shows a friendly message for known API error details', async () => {
    const send = vi.fn().mockRejectedValue(new ApiError(502, '{"detail":"llm_unavailable"}'))
    const wrapper = mount(AgentChatWidget, {
      props: { agentName: 'Mon agent', send },
    })

    await wrapper.find('textarea').setValue('Salut')
    await wrapper.find('button').trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('momentanément indisponible')
  })

  it('disables the send button while a request is in flight', async () => {
    let resolveSend: (value: { reply: string }) => void = () => {}
    const send = vi.fn(
      () => new Promise<{ reply: string }>((resolve) => (resolveSend = resolve)),
    )
    const wrapper = mount(AgentChatWidget, {
      props: { agentName: 'Mon agent', send },
    })

    await wrapper.find('textarea').setValue('Salut')
    await wrapper.find('button').trigger('click')

    expect(wrapper.find('button').attributes('disabled')).toBeDefined()

    resolveSend({ reply: 'ok' })
    await flushPromises()

    expect(wrapper.find('button').attributes('disabled')).toBeDefined() // empty input again
  })

  it('rend le Markdown des réponses de l’agent, pas celui de l’utilisateur', async () => {
    const send = vi.fn(async () => ({ reply: '1. **Simplifier** une procédure\n2. *Orienter* l’usager' }))
    const wrapper = mount(AgentChatWidget, { props: { agentName: 'Mon agent', send } })

    await wrapper.find('textarea').setValue('Mon **message**')
    await wrapper.find('button').trigger('click')
    await flushPromises()

    const html = wrapper.html()
    expect(html).toContain('<strong>Simplifier</strong>')
    expect(html).toContain('<em>Orienter</em>')
    expect(wrapper.find('ol').exists()).toBe(true)
    expect(wrapper.text()).toContain('Vous : Mon **message**')
    expect(wrapper.text()).not.toContain('**Simplifier**')
  })
})
