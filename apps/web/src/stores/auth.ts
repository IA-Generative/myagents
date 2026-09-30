import { defineStore } from 'pinia'
import { UserManager, WebStorageStateStore, type User as OidcUser } from 'oidc-client-ts'

// --- Configuration OIDC (Keycloak realm `myagents`) ---
// En local : http://localhost:8180/realms/myagents
const KEYCLOAK_URL = import.meta.env.VITE_KEYCLOAK_URL ?? 'http://localhost:8180'
const REALM = import.meta.env.VITE_KEYCLOAK_REALM ?? 'myagents'
const CLIENT_ID = import.meta.env.VITE_KEYCLOAK_CLIENT_ID ?? 'myagents-web'

const ISSUER = `${KEYCLOAK_URL.replace(/\/$/, '')}/realms/${REALM}`

const userManager = new UserManager({
  authority: ISSUER,
  client_id: CLIENT_ID,
  redirect_uri: `${window.location.origin}/callback`,
  post_logout_redirect_uri: `${window.location.origin}/`,
  response_type: 'code',
  scope: 'openid profile email roles',
  loadUserInfo: true,
  stateStore: new WebStorageStateStore({ store: window.sessionStorage }),
  userStore: new WebStorageStateStore({ store: window.sessionStorage }),
})

export interface AuthUser {
  id: string
  username: string
  email: string
  roles: string[]
  groups: string[]
  isAdmin: boolean
  accessToken: string
}

function mapUser(oidcUser: OidcUser): AuthUser {
  const profile = oidcUser.profile as Record<string, unknown> | undefined
  const realmAccess = (profile?.realm_access ?? {}) as { roles?: string[] }
  const roles: string[] = realmAccess.roles ?? []
  const groups: string[] = (profile?.groups as string[] | undefined) ?? []
  return {
    id: (profile?.sub as string) ?? '',
    username: (profile?.preferred_username as string) ?? '',
    email: (profile?.email as string) ?? '',
    roles,
    groups,
    isAdmin: roles.includes('admin') || groups.includes('/myagents-admin'),
    accessToken: oidcUser.access_token ?? '',
  }
}

interface AuthState {
  user: AuthUser | null
  loading: boolean
  error: string | null
}

export const useAuthStore = defineStore('auth', {
  state: (): AuthState => ({
    user: null,
    loading: false,
    error: null,
  }),
  getters: {
    isAuthenticated: (state) => state.user !== null,
    token: (state) => state.user?.accessToken ?? null,
  },
  actions: {
    async init() {
      this.loading = true
      try {
        const oidcUser = await userManager.getUser()
        this.user = oidcUser ? mapUser(oidcUser) : null
      } catch (e: unknown) {
        this.error = e instanceof Error ? e.message : 'init failed'
      } finally {
        this.loading = false
      }
    },
    async login(returnPath?: string) {
      await userManager.signinRedirect({
        state: returnPath ?? window.location.pathname,
      })
    },
    async handleCallback() {
      this.loading = true
      try {
        const oidcUser = await userManager.signinRedirectCallback()
        this.user = mapUser(oidcUser)
        return (oidcUser.state as string) ?? '/'
      } catch (e: unknown) {
        this.error = e instanceof Error ? e.message : 'callback failed'
        return '/'
      } finally {
        this.loading = false
      }
    },
    async logout() {
      await userManager.signoutRedirect()
    },
    async silentRenew() {
      try {
        const oidcUser = await userManager.signinSilent()
        this.user = oidcUser ? mapUser(oidcUser) : null
      } catch {
        this.user = null
      }
    },
  },
})

export { userManager }
