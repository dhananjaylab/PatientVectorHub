/// <reference types="vitest/config" />
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Phase 9: merged Vitest config into this file (single source of truth)
// rather than a separate vitest.config.ts — avoids the two configs
// silently drifting apart on plugin/resolve settings, which is a common
// real-world Vitest footgun when the app config and test config live in
// different files.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/v1': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
    css: false,
    // Each test file that does `vi.mock('../../lib/api')` shares ONE mock
    // module instance across every `it()` in that file — without this,
    // api.get's call-count and queued mockResolvedValueOnce()s bleed from
    // one test into the next (caught directly: useJobDetail's "does not
    // fire when jobId is undefined" test was failing because it saw call
    // counts left over from the two tests that ran before it in the same
    // file, not because the `enabled: false` guard was actually broken).
    clearMocks: true,
    // Deliberately no `globals: true` — describe/it/expect are imported
    // explicitly in every test file (see src/test/setup.ts's docstring),
    // matching this codebase's preference for explicit imports over
    // ambient globals elsewhere (e.g. crud.py's explicit str()/isoformat()
    // serialization rather than relying on implicit coercion).
    coverage: {
      provider: 'v8',
      reporter: ['text', 'html'],
      exclude: ['e2e/**', 'src/main.tsx', 'src/vite-env.d.ts', '**/*.config.ts'],
    },
    exclude: ['e2e/**', 'node_modules/**'],
  },
})
