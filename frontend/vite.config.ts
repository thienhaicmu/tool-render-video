import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'
import { fileURLToPath } from 'node:url'
import { dirname, resolve } from 'node:path'

// Path alias `@/*` → `src/*`. Mirrors tsconfig.app.json. Sprint 9 migration
// (audit followup_2): the tsconfig alias was declared since project init but
// Vite resolution was never configured, so imports stayed relative
// (`../../../api/...`). This block makes the alias usable at runtime + in tests.
const __dirname = dirname(fileURLToPath(import.meta.url))

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': resolve(__dirname, 'src'),
    },
  },
  server: {
    proxy: {
      '/api': { target: 'http://127.0.0.1:8000', changeOrigin: true, ws: true },
      '/media': 'http://127.0.0.1:8000',
    },
  },
  build: {
    outDir: '../backend/static-v2',
    emptyOutDir: true,
    rollupOptions: {
      output: {
        // Split the rarely-changing runtime into a long-cacheable vendor
        // chunk so app-code updates don't re-download React (F1).
        manualChunks: {
          vendor: ['react', 'react-dom', 'zustand'],
        },
      },
    },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./tests/setup.ts'],
  },
})
