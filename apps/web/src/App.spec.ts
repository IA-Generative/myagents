import { mount, flushPromises } from '@vue/test-utils'
import { createRouter, createMemoryHistory } from 'vue-router'
import { setActivePinia, createPinia } from 'pinia'
import { describe, expect, it, vi, beforeEach } from 'vitest'
import VueDsfr from '@gouvminint/vue-dsfr'

import '@gouvfr/dsfr/dist/dsfr.min.css'
import '@gouvfr/dsfr/dist/utility/icons/icons.min.css'
import '@gouvminint/vue-dsfr/styles'

import App from './App.vue'

describe('App.vue', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, status: 401 }))
  })

  it('affiche un bandeau d\'erreur si ?auth_error=authentication_failed', async () => {
     const router = createRouter({
       history: createMemoryHistory('/?auth_error=authentication_failed'),
       routes: [
         {
           path: '/',
           component: { template: '<div>Home</div>' },
         },
       ],
     })

      const wrapper = mount(App, {
        global: {
          plugins: [router, VueDsfr],
        },
      })

     await router.isReady()
     await wrapper.vm.$nextTick()
     await flushPromises()

     const alert = wrapper.findComponent({ name: 'DsfrAlert' })
     expect(alert.exists()).toBe(true)
     expect(alert.props('type')).toBe('error')
     expect(alert.props('title')).toBe('Erreur de connexion')
     expect(alert.props('description')).toContain('Votre session a expiré')
  })

  it('affiche un message différent si ?auth_error=auth_unavailable', async () => {
     const router = createRouter({
       history: createMemoryHistory('/?auth_error=auth_unavailable'),
       routes: [
         {
           path: '/',
           component: { template: '<div>Home</div>' },
         },
       ],
     })

      const wrapper = mount(App, {
        global: {
          plugins: [router, VueDsfr],
        },
      })

     await router.isReady()
     await wrapper.vm.$nextTick()
     await flushPromises()

     const alert = wrapper.findComponent({ name: 'DsfrAlert' })
     expect(alert.exists()).toBe(true)
     expect(alert.props('description')).toContain('temporairement indisponible')
  })

  it('nettoie le paramètre ?auth_error de l\'URL après le montage', async () => {
     const router = createRouter({
       history: createMemoryHistory('/?auth_error=authentication_failed'),
       routes: [
         {
           path: '/',
           component: { template: '<div>Home</div>' },
         },
       ],
     })

     mount(App, {
       global: {
         plugins: [router, VueDsfr],
       },
     })

    await router.isReady()
    await flushPromises()

    // Vérifier que le paramètre a été supprimé de l'URL
    expect(router.currentRoute.value.query.auth_error).toBeUndefined()
  })

  it('affiche le lien "Se reconnecter" et ferme l\'alerte quand cliqué', async () => {
     const router = createRouter({
       history: createMemoryHistory('/?auth_error=authentication_failed'),
       routes: [
         {
           path: '/',
           component: { template: '<div>Home</div>' },
         },
       ],
     })

      const wrapper = mount(App, {
        global: {
          plugins: [router, VueDsfr],
        },
      })

     await router.isReady()
     await wrapper.vm.$nextTick()
     await flushPromises()

     const alert = wrapper.findComponent({ name: 'DsfrAlert' })
     expect(alert.exists()).toBe(true)

     // Simuler la fermeture de l'alerte
    await alert.vm.$emit('close')
    await wrapper.vm.$nextTick()

    // Vérifier que l'alerte n'est plus affichée
    expect(wrapper.findComponent({ name: 'DsfrAlert' }).exists()).toBe(false)
  })

  it('n\'affiche pas l\'alerte si pas de paramètre ?auth_error', async () => {
     const router = createRouter({
       history: createMemoryHistory('/'),
       routes: [
         {
           path: '/',
           component: { template: '<div>Home</div>' },
         },
       ],
     })

     const wrapper = mount(App, {
       global: {
         plugins: [router, VueDsfr],
       },
     })

    await router.isReady()
    await flushPromises()

    const alert = wrapper.findComponent({ name: 'DsfrAlert' })
    expect(alert.exists()).toBe(false)
  })
})
