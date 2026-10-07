// Relative by default so the browser calls the same origin it was loaded from
// (works both on localhost and behind a forwarded/tunneled dev URL); see the
// Vite dev-server proxy in vite.config.ts.
const BASE_URL = import.meta.env.VITE_API_URL ?? '/api'

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message)
  }
}

// Authentification : cookie de session HttpOnly posé par le server ; l'en-tête custom sert de
// garde CSRF pour les requêtes mutantes (refusées par le server sans lui).
const CSRF_HEADERS = { 'X-Requested-With': 'XMLHttpRequest' }

// Sur 401 (session absente ou expirée) : retour vers le login mené par le server.
async function fetchWithAuth(path: string, init: RequestInit): Promise<Response> {
  const res = await fetch(`${BASE_URL}${path}`, {
    ...init,
    credentials: 'same-origin',
    headers: { ...CSRF_HEADERS, ...init.headers },
  })
  if (res.status === 401) {
    const { useAuthStore } = await import('@/stores/auth')
    useAuthStore().login()
  }
  if (!res.ok) {
    const body = await res.text().catch(() => '')
    throw new ApiError(res.status, body || res.statusText)
  }
  return res
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const res = await fetchWithAuth(path, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...init.headers },
  })
  if (res.status === 204) return undefined as T
  return (await res.json()) as T
}

export const api = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: 'POST', body: body ? JSON.stringify(body) : undefined }),
  put: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: 'PUT', body: body ? JSON.stringify(body) : undefined }),
  delete: <T>(path: string) => request<T>(path, { method: 'DELETE' }),
  // No Content-Type override: the browser sets the multipart boundary itself.
  postForm: async <T>(path: string, form: FormData) => {
    const res = await fetchWithAuth(path, { method: 'POST', body: form })
    return (await res.json()) as T
  },
}

export interface StreamChatCallbacks {
  onToken?: (content: string) => void
  onToolCall?: (toolName: string, args: Record<string, unknown>) => void
  onToolResult?: (toolName: string, result: string) => void
  onBlocked?: (message: string) => void
  onDone?: (conversationId?: string) => void
  onError?: (message: string) => void
}

export async function streamChat(
  path: string,
  body: unknown,
  callbacks: StreamChatCallbacks,
  signal?: AbortSignal,
): Promise<void> {
  const res = await fetch(`${BASE_URL}${path}`, {
    method: 'POST',
    credentials: 'same-origin',
    headers: {
      'Content-Type': 'application/json',
      ...CSRF_HEADERS,
    },
    body: JSON.stringify(body),
    signal,
  })

  if (res.status === 401) {
    const { useAuthStore } = await import('@/stores/auth')
    useAuthStore().login()
    return
  }

  if (!res.ok) {
    const text = await res.text().catch(() => '')
    callbacks.onError?.(text || res.statusText)
    return
  }

  const reader = res.body?.getReader()
  if (!reader) {
    callbacks.onError?.('Stream not available')
    return
  }

  const decoder = new TextDecoder()
  let buffer = ''
  let conversationId: string | undefined

  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })

      const lines = buffer.split('\n')
      buffer = lines.pop() ?? ''

      for (const line of lines) {
        const trimmed = line.trim()
        if (!trimmed || !trimmed.startsWith('data: ')) continue
        const data = trimmed.slice(6)
        if (data === '[DONE]') {
          callbacks.onDone?.(conversationId)
          return
        }
        try {
          const event = JSON.parse(data) as {
            type: string
            content?: string
            tool_name?: string
            tool_args?: Record<string, unknown>
            tool_result?: string
            conversation_id?: string
          }
          if (event.conversation_id) conversationId = event.conversation_id
          switch (event.type) {
            case 'token':
              callbacks.onToken?.(event.content ?? '')
              break
            case 'tool_call':
              callbacks.onToolCall?.(event.tool_name ?? '', event.tool_args ?? {})
              break
            case 'tool_result':
              callbacks.onToolResult?.(event.tool_name ?? '', event.tool_result ?? '')
              break
            case 'blocked':
              callbacks.onBlocked?.(event.content ?? '')
              break
            case 'done':
              callbacks.onDone?.(conversationId)
              return
            case 'error':
              callbacks.onError?.(event.content ?? 'unknown error')
              break
          }
        } catch {
          // ignore malformed JSON
        }
      }
    }
  } finally {
    reader.releaseLock()
  }
  callbacks.onDone?.(conversationId)
}
