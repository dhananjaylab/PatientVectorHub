/**
 * dashboard/playwright.config.ts
 *
 * New in Phase 9. package.json has had @playwright/test as a
 * devDependency and a `test:e2e` script since Phase 1, but this config
 * file never existed — `npm run test:e2e` would have failed immediately
 * on "no config found," same broken-since-scaffold story as
 * lib/api.ts / lib/keycloak.ts.
 *
 * These specs exercise the app against a REAL running backend (`make
 * dev` + `npm run dev`), not a mocked one — unlike the Vitest unit
 * tests, which mock `lib/api` entirely. That's a deliberate scope
 * boundary, not an oversight: wiring a full docker-compose stack
 * (Postgres/Redis/Keycloak/Kafka/Weaviate) into GitHub Actions for
 * every PR is real infra work of its own, called out as a follow-up in
 * docs/PHASE_9_IMPLEMENTATION_PLAN.md §7 rather than folded silently
 * into this phase's CI job. `npm run test:e2e` is meant to be run
 * locally against `make dev`, or in a future dedicated e2e CI job.
 */
import { defineConfig, devices } from '@playwright/test'

export default defineConfig({
  testDir: './e2e',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: process.env.CI ? 'github' : 'html',
  use: {
    baseURL: process.env.PVH_E2E_BASE_URL ?? 'http://localhost:5173',
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
      // Phase 11 / ADR-018 Stage 11.3: explicitly scoped to the specs
      // that predate role-diverse auth, now that rbac-navigation.spec.ts
      // exists alongside them in the same testDir. Without this,
      // chromium's default (unrestricted) testMatch would also collect
      // rbac-navigation.spec.ts and run its per-role assertions against
      // an AUTH_ENABLED=false session that is always readonly regardless
      // of which role project name Playwright thinks it's running under
      // -- every non-readonly assertion in that file would fail for a
      // reason that has nothing to do with RBAC actually being broken.
      testMatch: ['dashboard.spec.ts', 'navigation.spec.ts'],
    },
    // Phase 11 / ADR-018 Stage 11.3 -- role-diverse coverage, additive
    // to the 'chromium' project above (which keeps running the
    // existing AUTH_ENABLED=false specs unchanged). These 5 projects
    // only run when the target stack has VITE_AUTH_ENABLED=true and a
    // real Keycloak reachable -- not meaningful against the plain
    // `npm run dev` webServer this config starts by default, so they
    // require PVH_E2E_BASE_URL pointed at a real auth-enabled stack
    // (see the new e2e CI job, workflow_dispatch only).
    {
      name: 'setup',
      testMatch: /auth\.setup\.ts/,
    },
    {
      name: 'admin',
      use: { ...devices['Desktop Chrome'], storageState: 'e2e/.auth/admin.json' },
      dependencies: ['setup'],
      testMatch: 'rbac-navigation.spec.ts',
    },
    {
      name: 'engineer',
      use: { ...devices['Desktop Chrome'], storageState: 'e2e/.auth/engineer.json' },
      dependencies: ['setup'],
      testMatch: 'rbac-navigation.spec.ts',
    },
    {
      name: 'analyst',
      use: { ...devices['Desktop Chrome'], storageState: 'e2e/.auth/analyst.json' },
      dependencies: ['setup'],
      testMatch: 'rbac-navigation.spec.ts',
    },
    {
      name: 'auditor',
      use: { ...devices['Desktop Chrome'], storageState: 'e2e/.auth/auditor.json' },
      dependencies: ['setup'],
      testMatch: 'rbac-navigation.spec.ts',
    },
    {
      name: 'readonly',
      use: { ...devices['Desktop Chrome'], storageState: 'e2e/.auth/readonly.json' },
      dependencies: ['setup'],
      testMatch: 'rbac-navigation.spec.ts',
    },
  ],
  // Starts the Vite dev server automatically for local runs; in CI this
  // is skipped in favor of an explicitly-started stack (see the future
  // e2e workflow job referenced above) so Playwright doesn't try to
  // spin up `npm run dev` against a backend that isn't there yet.
  webServer: process.env.CI
    ? undefined
    : {
        command: 'npm run dev',
        url: 'http://localhost:5173',
        reuseExistingServer: true,
        timeout: 30_000,
      },
})
