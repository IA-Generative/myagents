import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', redirect: '/agents' },
    { path: '/callback', name: 'auth-callback', component: () => import('@/pages/AuthCallbackPage.vue') },
    { path: '/agents', name: 'agents', component: () => import('@/pages/AgentsListPage.vue') },
    {
      path: '/agents/new',
      name: 'agent-new',
      component: () => import('@/pages/AgentWizardPage.vue'),
    },
    {
      path: '/agents/:id/edit',
      name: 'agent-edit',
      component: () => import('@/pages/AgentWizardPage.vue'),
      props: true,
    },
    { path: '/catalog', name: 'catalog', component: () => import('@/pages/CatalogPage.vue') },
    {
      path: '/catalog/:id',
      name: 'catalog-detail',
      component: () => import('@/pages/AgentDetailPage.vue'),
      props: true,
    },
  ],
})

// Garde d'authentification : redirige vers Keycloak si non authentifié.
router.beforeEach(async (to) => {
  if (to.name === 'auth-callback') return true
  const auth = useAuthStore()
  if (auth.loading) return false
  if (!auth.user) await auth.init()
  if (!auth.isAuthenticated) {
    await auth.login(to.fullPath)
    return false
  }
  return true
})
