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
