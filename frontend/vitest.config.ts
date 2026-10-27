import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';
import path from 'path';

/**
 * Vitest configuration for React component unit tests
 * @see https://vitest.dev/config/
 */
export default defineConfig({
  plugins: [react()],

  test: {
    // Use jsdom environment for React component testing
    environment: 'jsdom',

    // Setup files to run before each test file
    setupFiles: ['./tests/setup.ts'],

    // Enable global test APIs (describe, it, expect, etc.)
    globals: true,

    // Coverage configuration
    coverage: {
      provider: 'v8',
      reporter: ['text', 'json', 'html', 'lcov'],
      exclude: [
        'node_modules/',
        'tests/',
        '*.config.ts',
        '*.config.js',
        'dist/',
        'src/main.tsx',
      ],
      // Minimum coverage thresholds
      lines: 70,
      functions: 70,
      branches: 70,
      statements: 70,
    },

    // Test file patterns
    include: ['**/*.{test,spec}.{ts,tsx}'],
    exclude: ['node_modules', 'dist', 'tests/e2e', 'tests/visual', '**/vite.config.test.ts'],
  },

  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
});
