// Client Scaleway Generative APIs — protocole OpenAI-compatible.
// Utilisé UNIQUEMENT côté serveur (routes BFF) pour que la clé
// SCW_SECRET_KEY_LLM ne fuite jamais côté client.
//
// Endpoint : https://api.scaleway.ai/<PROJECT_ID>/v1/chat/completions
// Auth     : Authorization: Bearer <SCW_SECRET_KEY_LLM>
// Pattern  : identique à celui utilisé par OpenWebUI dans owuicore-main
//            (RAG_OPENAI_API_BASE_URL + RAG_OPENAI_API_KEY).

import { env } from './env';

export type ChatMessage = {
  role: 'system' | 'user' | 'assistant';
  content: string;
};

export type ChatCompletion = {
  choices: Array<{
    message: { role: string; content: string };
    finish_reason?: string;
  }>;
  usage?: {
    prompt_tokens: number;
    completion_tokens: number;
    total_tokens: number;
  };
};

export class ScwLlmUnavailableError extends Error {
  constructor() {
    super(
      'Scaleway LLM non configuré — SCW_LLM_BASE_URL et/ou SCW_SECRET_KEY_LLM manquants.',
    );
    this.name = 'ScwLlmUnavailableError';
  }
}

export async function scwListModels(): Promise<Array<{ id: string; owned_by?: string }>> {
  const e = env();
  if (!e.SCW_LLM_BASE_URL || !e.SCW_SECRET_KEY_LLM) {
    throw new ScwLlmUnavailableError();
  }
  const url = `${e.SCW_LLM_BASE_URL.replace(/\/$/, '')}/models`;
  const res = await fetch(url, {
    headers: { Authorization: `Bearer ${e.SCW_SECRET_KEY_LLM}` },
    signal: AbortSignal.timeout(10000),
  });
  if (!res.ok) {
    const detail = await res.text().catch(() => '');
    throw new Error(`Scaleway models ${res.status}: ${detail.slice(0, 300)}`);
  }
  const json = (await res.json()) as { data?: Array<{ id: string; owned_by?: string }> };
  return json.data ?? [];
}

export async function scwChatCompletions(params: {
  messages: ChatMessage[];
  model?: string;
  temperature?: number;
  maxTokens?: number;
}): Promise<ChatCompletion> {
  const e = env();
  if (!e.SCW_LLM_BASE_URL || !e.SCW_SECRET_KEY_LLM) {
    throw new ScwLlmUnavailableError();
  }

  const url = `${e.SCW_LLM_BASE_URL.replace(/\/$/, '')}/chat/completions`;
  const res = await fetch(url, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${e.SCW_SECRET_KEY_LLM}`,
    },
    body: JSON.stringify({
      model: params.model ?? e.SCW_LLM_MODEL,
      messages: params.messages,
      temperature: params.temperature ?? 0.7,
      // gpt-oss-120b est un modèle "reasoning" : il génère des tokens de
      // raisonnement AVANT le contenu. Avec un budget trop serré (< 500),
      // le content sort à null. On met 2048 par défaut pour laisser de la
      // marge même sur les prompts longs.
      max_tokens: params.maxTokens ?? 2048,
      stream: false,
    }),
  });

  if (!res.ok) {
    const detail = await res.text().catch(() => '');
    throw new Error(`Scaleway LLM ${res.status}: ${detail.slice(0, 500)}`);
  }

  return (await res.json()) as ChatCompletion;
}
