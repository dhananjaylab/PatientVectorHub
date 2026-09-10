/**
 * dashboard/e2e/rbac-navigation.spec.ts — Phase 11 / ADR-018 Stage 11.3.
 *
 * Runs under the 5 authenticated role projects added to
 * playwright.config.ts this phase (admin/engineer/analyst/auditor/
 * readonly), each with a real storageState from auth.setup.ts's actual
 * Keycloak login -- unlike navigation.spec.ts's existing "sidebar only
 * shows nav links a readonly role can access" test, which can only
 * ever prove that one role, because AUTH_ENABLED=false forces every
 * caller to readonly regardless of who's asking.
 *
 * Expected visibility sourced directly from
 * dashboard/src/components/layout/AppLayout.tsx's NAV_ITEMS array
 * (each item's `min` role) and lib/rbac.ts's hasMinRole() hierarchy
 * (admin=4 > engineer=3 > analyst=2 > auditor=1 > readonly=0) --
 * not re-derived or guessed here. Notably, analyst (2) satisfies
 * Audit Logs' own floor of auditor (1) via >=, so analyst sees Audit
 * Logs too, despite the name -- this is the real, current hierarchy
 * behavior on both frontend and backend (audit.py's own
 * require_min_role("auditor") for GET /logs), not a test assumption.
 *
 * This project's chromium project (the pre-existing one) is scoped
 * away from this file via testMatch in playwright.config.ts, so the
 * two suites never run against each other's wrong auth mode.
 */
import { test, expect, type Page } from "@playwright/test";

type Role = "admin" | "engineer" | "analyst" | "auditor" | "readonly";

const EXPECTED_VISIBLE_NAV: Record<Role, string[]> = {
  admin: ["Dashboard", "Ingestion", "Query", "Audit Logs", "Admin"],
  engineer: ["Dashboard", "Ingestion", "Query", "Audit Logs"],
  analyst: ["Dashboard", "Query", "Audit Logs"],
  auditor: ["Dashboard", "Audit Logs"],
  readonly: ["Dashboard"],
};

const ALL_NAV_LABELS = ["Dashboard", "Ingestion", "Query", "Audit Logs", "Admin"];

function currentRole(page: Page, projectName: string): Role {
  const role = projectName as Role;
  if (!(role in EXPECTED_VISIBLE_NAV)) {
    throw new Error(
      `rbac-navigation.spec.ts run under an unexpected project "${projectName}" ` +
        `-- only admin/engineer/analyst/auditor/readonly are meaningful here.`
    );
  }
  return role;
}

test.describe("RBAC-aware navigation (real Keycloak session per role)", () => {
  test("sidebar shows exactly the nav links this role's floor allows", async ({
    page,
  }, testInfo) => {
    const role = currentRole(page, testInfo.project.name);
    await page.goto("/dashboard");

    const expectedVisible = new Set(EXPECTED_VISIBLE_NAV[role]);
    for (const label of ALL_NAV_LABELS) {
      const link = page.getByRole("link", { name: label });
      if (expectedVisible.has(label)) {
        await expect(link).toBeVisible();
      } else {
        await expect(link).toHaveCount(0);
      }
    }
  });

  test("the correct role pill is shown in the top bar", async ({ page }, testInfo) => {
    const role = currentRole(page, testInfo.project.name);
    await page.goto("/dashboard");
    const label = role.charAt(0).toUpperCase() + role.slice(1);
    await expect(page.getByText(label, { exact: true })).toBeVisible();
  });

  test("visiting a route above this role's floor shows 403, not a crash", async ({
    page,
  }, testInfo) => {
    const role = currentRole(page, testInfo.project.name);
    if (role === "admin") {
      test.skip(true, "admin has no route it should be refused from");
      return;
    }
    // Admin is always the route one step above every other role's own
    // ceiling in this nav structure -- a single well-chosen probe
    // route, rather than every possible over-reach per role.
    await page.goto("/admin");
    await expect(page.getByText(/403/)).toBeVisible();
  });
});
