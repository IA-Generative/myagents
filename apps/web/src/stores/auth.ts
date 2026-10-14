import { defineStore } from 'pinia'

// L'authentification est menée par le server (cookie de session HttpOnly) : ce store ne voit
// jamais de jeton, il ne fait que demander « qui suis-je ? » et rediriger vers /api/auth.
const BASE_URL = import.meta.env.VITE_API_URL ?? '/api'

export interface AuthUser {
  id: string
  username: string
  email: string
  roles: string[]
  groups: string[]
  isAdmin: boolean
}

interface AuthMe {
  id: string
  username: string
  email: string
  roles: string[]
  groups: string[]
  is_admin: boolean
  sso_enabled: boolean
}

interface AuthState {
  user: AuthUser | null
  ssoEnabled: boolean
  loading: boolean
  error: string | null
}

// Un seul /auth/me en vol : la garde du routeur et App.vue l'appellent en même temps au démarrage.
let pendingInit: Promise<void> | null = null

export const useAuthStore = defineStore('auth', {
  state: (): AuthState => ({
    user: null,
    ssoEnabled: false,
    loading: false,
    error: null,
  }),
  getters: {
    isAuthenticated: (state) => state.user !== null,
  },
  actions: {
    init() {
      pendingInit ??= this.loadUser().finally(() => {
        pendingInit = null
      })
      return pendingInit
    },
    async loadUser() {
      this.loading = true
      this.error = null
      try {
        const res = await fetch(`${BASE_URL}/auth/me`, { credentials: 'same-origin' })
        if (res.ok) {
          const me = (await res.json()) as AuthMe
          this.user = {
            id: me.id,
            username: me.username,
            email: me.email,
            roles: me.roles,
            groups: me.groups,
            isAdmin: me.is_admin,
          }
          this.ssoEnabled = me.sso_enabled
        } else {
          this.user = null
        }
      } catch (e: unknown) {
        this.user = null
        this.error = e instanceof Error ? e.message : 'init failed'
      } finally {
        this.loading = false
      }
    },
    login(returnPath?: string) {
      const target = returnPath ?? window.location.pathname + window.location.search
      window.location.assign(`${BASE_URL}/auth/login?return_to=${encodeURIComponent(target)}`)
    },
    async logout() {
      const res = await fetch(`${BASE_URL}/auth/logout`, {
        method: 'POST',
        credentials: 'same-origin',
        headers: { 'X-Requested-With': 'XMLHttpRequest' },
      })
      this.user = null
      const body = res.ok ? ((await res.json()) as { logout_url?: string }) : {}
      window.location.assign(body.logout_url ?? '/')
    },
  },
})
