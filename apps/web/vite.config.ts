import { fileURLToPath, URL } from 'node:url'

import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  // Single source of truth for local dev config: the repo-root .env (next to docker-compose.yml).
  envDir: fileURLToPath(new URL('../..', import.meta.url)),
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  server: {
    host: true,
    port: 5173,
    allowedHosts: ['.dev.forge.minint.fr'],
    proxy: {
      // Lets the browser call same-origin `/api/...` (works both on localhost and
      // behind a forwarded/tunneled dev URL); Vite forwards server-side to the API.
      '/api': {
        target: process.env.API_PROXY_TARGET ?? 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
})
