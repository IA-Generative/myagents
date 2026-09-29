import { api } from './client'
import type { OnboardingAgentConfig, OnboardingMessage } from '@/types/agent'

export const promptApi = {
  assist: (prompt: string, hints: Record<string, string> = {}) =>
    api.post<{ prompt: string }>('/agents/prompt/assist', { prompt, hints }),
  optimize: (prompt: string) => api.post<{ prompt: string }>('/agents/prompt/optimize', { prompt }),
  suggestStarters: (prompt: string, count = 4) =>
    api.post<{ greeting: string; examples: string[] }>('/agents/prompt/suggest-starters', {
      prompt,
      count,
    }),
  validate: (prompt: string) =>
    api.post<{ ok: boolean; message: string | null }>('/agents/prompt/validate', { prompt }),
  onboardingChat: (messages: OnboardingMessage[]) =>
    api.post<{ message: string; agent_config: OnboardingAgentConfig | null }>(
      '/agents/onboarding-chat',
      { messages },
    ),
}
