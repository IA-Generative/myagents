import { setActivePinia, createPinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { useAuthStore } from '@/stores/auth'

const me = {
  id: 'user-1',
  username: 'alice',
  email: 'alice@example.org',
  roles: ['user'],
  groups: [],
  is_admin: false,
}

describe('auth store (session gérée par le server)', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('init charge l\'utilisateur depuis /api/auth/me sans manipuler de jeton', async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => me })
    vi.stubGlobal('fetch', fetchMock)
    const auth = useAuthStore()

    await auth.init()

    expect(auth.user?.username).toBe('alice')
    expect(auth.user?.isAdmin).toBe(false)
    expect(fetchMock).toHaveBeenCalledWith('/api/auth/me', { credentials: 'same-origin' })
    expect(sessionStorage.length).toBe(0)
    expect(localStorage.length).toBe(0)
  })

  it('init concurrents (garde du routeur + App.vue) : un seul appel /auth/me', async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => me })
    vi.stubGlobal('fetch', fetchMock)
    const auth = useAuthStore()

    await Promise.all([auth.init(), auth.init()])

    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(auth.isAuthenticated).toBe(true)
  })

  it('init laisse l\'utilisateur à null sur 401', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, status: 401 }))
    const auth = useAuthStore()

    await auth.init()

    expect(auth.isAuthenticated).toBe(false)
  })

  it('login redirige vers le login du server avec un chemin relatif', () => {
    const assign = vi.fn()
    vi.stubGlobal('location', { assign, pathname: '/catalog', search: '?q=a' })

    useAuthStore().login()

    expect(assign).toHaveBeenCalledWith('/api/auth/login?return_to=%2Fcatalog%3Fq%3Da')
  })

  it('logout appelle POST /api/auth/logout puis suit l\'URL de déconnexion Keycloak', async () => {
    const assign = vi.fn()
    vi.stubGlobal('location', { assign })
    const fetchMock = vi
      .fn()
      .mockResolvedValue({ ok: true, json: async () => ({ logout_url: 'https://sso.example/logout' }) })
    vi.stubGlobal('fetch', fetchMock)
    const auth = useAuthStore()
    auth.user = { id: '1', username: 'a', email: '', roles: [], groups: [], isAdmin: false }

    await auth.logout()

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/auth/logout',
      expect.objectContaining({
        method: 'POST',
        headers: { 'X-Requested-With': 'XMLHttpRequest' },
      }),
    )
    expect(assign).toHaveBeenCalledWith('https://sso.example/logout')
    expect(auth.user).toBeNull()
  })
})
