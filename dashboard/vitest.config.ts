import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: ['./src/test-setup.ts'],
    // Use threads pool with max 2 to avoid worker startup issues
    pool: 'threads',
    maxThreads: 2,
    minThreads: 1,
    testTimeout: 30000,
    hookTimeout: 120000,
    // Exclude e2e tests (those are for Playwright)
    exclude: ['e2e/**/*.spec.ts', 'node_modules/**'],
  },
});
