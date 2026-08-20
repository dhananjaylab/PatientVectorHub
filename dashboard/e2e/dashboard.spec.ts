/**
 * dashboard/e2e/dashboard.spec.ts
 *
 * Same readonly-only constraint as navigation.spec.ts — see that file's
 * docstring. Worth calling out here specifically: DashboardPage.tsx's
 * three summary cards (Active ingestion jobs, Vector store,
 * RAG query CTA) ALL require engineer+ or analyst+, so a readonly
 * visitor — the only role reachable in this test run — sees the
 * "Overview" heading and an empty grid, nothing else. That's real,
 * current behavior worth having a test lock in, not a gap in this
 * spec: if DashboardPage ever grows a readonly-visible card, this test
 * should be the one that needs updating alongside it.
 */
import { test, expect } from '@playwright/test'

test.describe('Dashboard (readonly)', () => {
  test('shows the Overview heading with no summary cards for a readonly visitor', async ({ page }) => {
    await page.goto('/dashboard')
    await expect(page.getByRole('heading', { name: 'Overview' })).toBeVisible()
    await expect(page.getByText('Active ingestion jobs')).toHaveCount(0)
    await expect(page.getByText('Vector store')).toHaveCount(0)
    await expect(page.getByText('Run a query')).toHaveCount(0)
  })

  test('does not show the "Recent activity" section either (also gated behind engineer+)', async ({ page }) => {
    await page.goto('/dashboard')
    await expect(page.getByRole('heading', { name: 'Recent activity' })).toHaveCount(0)
  })
})
