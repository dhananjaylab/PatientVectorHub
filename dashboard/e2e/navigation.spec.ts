/**
 * dashboard/e2e/navigation.spec.ts
 *
 * Written against the app's actual local-dev default: AUTH_ENABLED=false
 * (api-gateway/src/config.py) plus VITE_AUTH_ENABLED=false
 * (.env.example) — verified this phase, and worth stating plainly since
 * it's not what "auth disabled" might suggest: it does NOT mean
 * unrestricted access. deps.py's get_current_user() and
 * middleware/rbac.py's require_role()/require_min_role() both default
 * an unset request.state.role to "readonly" — with no auth middleware
 * mounted at all (main.py only adds KeycloakJWTMiddleware when
 * AUTH_ENABLED=true), request.state.role is never set by anything else
 * either. So a AUTH_ENABLED=false backend enforces 'readonly' for
 * EVERY caller, frontend included — this is real, current backend
 * behavior, not a frontend design choice.
 *
 * Practical consequence for this file: readonly is the only role this
 * suite can exercise end-to-end against `make dev` as it stands today.
 * Covering engineer/analyst/auditor/admin flows needs either
 * VITE_AUTH_ENABLED=true with real seeded Keycloak users of each role
 * (not present in infra/keycloak/realm.json as of this phase), or a
 * deliberate test-only auth bypass — both are product/infra decisions
 * for someone to make explicitly, not something to fake here. See
 * docs/PHASE_9_IMPLEMENTATION_PLAN.md §7.
 */
import { test, expect } from '@playwright/test'

test.describe('Navigation (readonly / auth-disabled default)', () => {
  test('loads the dashboard at / and redirects to /dashboard', async ({ page }) => {
    await page.goto('/')
    await expect(page).toHaveURL(/\/dashboard$/)
    await expect(page.getByRole('heading', { name: 'Overview' })).toBeVisible()
  })

  test('sidebar only shows nav links a readonly role can access', async ({ page }) => {
    await page.goto('/dashboard')
    await expect(page.getByRole('link', { name: 'Dashboard' })).toBeVisible()
    await expect(page.getByRole('link', { name: 'Ingestion' })).toHaveCount(0)
    await expect(page.getByRole('link', { name: 'Query' })).toHaveCount(0)
    await expect(page.getByRole('link', { name: 'Audit Logs' })).toHaveCount(0)
    await expect(page.getByRole('link', { name: 'Admin' })).toHaveCount(0)
  })

  test('directly visiting a role-gated route shows a 403, not a crash', async ({ page }) => {
    await page.goto('/ingestion')
    await expect(page.getByText(/403/)).toBeVisible()
  })

  test('an unknown route renders the 404 page with a way back', async ({ page }) => {
    await page.goto('/this-page-does-not-exist')
    await expect(page.getByRole('heading', { name: '404 — Not Found' })).toBeVisible()
    await page.getByRole('link', { name: /Back to Dashboard/ }).click()
    await expect(page).toHaveURL(/\/dashboard$/)
  })

  test('the readonly role pill is visible in the top bar', async ({ page }) => {
    await page.goto('/dashboard')
    await expect(page.getByText('Readonly')).toBeVisible()
  })
})
