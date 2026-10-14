/// <reference types="vite/client" />

declare module '*.vue' {
  import type { DefineComponent } from 'vue'
  const component: DefineComponent<object, object, unknown>
  export default component
}

// Sous-chemin d'export CSS sans extension : non couvert par les déclarations *.css de vite/client.
declare module '@gouvminint/vue-dsfr/styles'

interface ImportMetaEnv {
  readonly VITE_API_URL: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
