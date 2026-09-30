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

// Lazy import to avoid a circular dependency (auth store imports nothing from api).
async function authHeaders(): Promise<Record<string, string>> {
  const { useAuthStore } = await import('@/stores/auth')
  const auth = useAuthStore()
  return auth.token ? { Authorization: `Bearer ${auth.token}` } : {}
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = { 'Content-Type': 'application/json', ...init?.headers, ...(await authHeaders()) }
  const res = await fetch(`${BASE_URL}${path}`, {
    ...init,
    headers,
  })
  if (!res.ok) {
    const body = await res.text().catch(() => '')
    throw new ApiError(res.status, body || res.statusText)
  }
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
    const headers = await authHeaders()
    const res = await fetch(`${BASE_URL}${path}`, { method: 'POST', body: form, headers })
    if (!res.ok) {
      const body = await res.text().catch(() => '')
      throw new ApiError(res.status, body || res.statusText)
    }
    return (await res.json()) as T
  },
}
