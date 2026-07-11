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
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:7317',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ''),
      },
    },
  },
})
