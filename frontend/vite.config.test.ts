import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

/**
 * Vite configuration for Playwright tests.
 *
 * Key difference from main config: NO PROXY for /api routes.
 * This allows Playwright to intercept API requests at the browser level
 * and return mocked responses without needing a real backend.
 */
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    port: 5174, // Different port for test server
    strictPort: true,
    // No proxy - requests will go directly to browser where Playwright can mock them
  },
})
