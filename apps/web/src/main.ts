import { createApp } from 'vue'
import { createPinia } from 'pinia'
import VueDsfr from '@gouvminint/vue-dsfr'

import '@gouvfr/dsfr/dist/dsfr.min.css'
import '@gouvfr/dsfr/dist/utility/icons/icons.min.css'
import '@gouvminint/vue-dsfr/styles'

import App from './App.vue'
import { chargerMenuCommun } from './menuCommun'
import { router } from './router'

createApp(App).use(createPinia()).use(router).use(VueDsfr).mount('#app')
chargerMenuCommun()
