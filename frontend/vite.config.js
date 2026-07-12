import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { fileURLToPath, URL } from 'node:url'

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      // Extensions import the stable host surface from this alias only (plan 04).
      'devicekit-sdk': fileURLToPath(new URL('./src/extensions/sdk/index.js', import.meta.url)),
    },
  },
  server: {
    port: 7318,
    fs: {
      // @tramo/editor + @tramo/spec are file:-linked from the sibling tramo repo
      // (plan 22 phase 6) — allow the dev server to serve their real paths.
      allow: ['.', fileURLToPath(new URL('../../tramo', import.meta.url))],
    },
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:7317',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ''),
      },
    },
  },
})
