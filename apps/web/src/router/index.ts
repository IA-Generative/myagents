import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

// Pages légales du pied de page DSFR (liens par défaut de DsfrFooter), accessibles sans connexion.
const legalPages = [
  { path: '/a11y', title: 'Accessibilité' },
  { path: '/mentions-legales', title: 'Mentions légales' },
  { path: '/donnees-personnelles', title: 'Données personnelles' },
  { path: '/cookies', title: 'Gestion des cookies' },
]

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', redirect: '/agents' },
    ...legalPages.map(({ path, title }) => ({
      path,
      component: () => import('@/pages/LegalPage.vue'),
      meta: { public: true, title },
    })),
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
    { path: '/chat', name: 'chat', component: () => import('@/pages/ChatPage.vue') },
  ],
})

// Garde d'authentification : redirige vers le login du server (Keycloak) si non authentifié.
router.beforeEach(async (to) => {
  if (to.meta.public) return true
  const auth = useAuthStore()
  if (!auth.user) await auth.init()
  if (!auth.isAuthenticated) {
    auth.login(to.fullPath)
    return false
  }
  return true
})
