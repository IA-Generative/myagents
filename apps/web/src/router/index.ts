import { createRouter, createWebHistory } from 'vue-router'

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', redirect: '/agents' },
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
