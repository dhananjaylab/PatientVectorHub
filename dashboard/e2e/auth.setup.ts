/**
 * dashboard/e2e/auth.setup.ts — Phase 11 / ADR-018 Stage 11.3.
 *
 * Performs a REAL Keycloak login (filling the actual hosted login
 * form Keycloak serves, the same page a real user hits) once per
 * role, and saves the resulting storageState -- the current standard
 * pattern for role-based Playwright suites (a `setup` project other
 * projects depend on, per Playwright's own project-dependencies
 * feature).
 *
 * Requires VITE_AUTH_ENABLED=true and a real Keycloak reachable at
 * VITE_KEYCLOAK_URL (see dashboard/src/lib/keycloak.ts) -- the existing
 * dashboard.spec.ts / navigation.spec.ts suite runs with
 * AUTH_ENABLED=false instead, which is *why* every existing spec only
 * ever exercises the readonly path (documented directly in
 * navigation.spec.ts's own comments). This file, and the 5 role
 * projects in playwright.config.ts that depend on it, are additive --
 * they don't replace or modify that existing no-auth suite.
 *
 * Credentials come from infra/keycloak/realm.json's seeded users
 * (test-password-123, tenant1). Four of five roles
 * (admin/engineer/analyst/auditor) were already seeded before this
 * phase; `readonly@tenant1.test` was added this phase -- the only
 * role that had no dedicated user.
 */
import { test as setup, expect } from "@playwright/test";
import path from "path";
import { fileURLToPath } from "url";

// __dirname doesn't exist in ES module scope (this project has
// "type": "module" in package.json) -- verified directly: tsc's
// --noEmit didn't catch this (it type-checks fine, since @types/node
// declares __dirname globally regardless of actual runtime module
// system), but Playwright's own test loader failed immediately with
// "ReferenceError: __dirname is not defined in ES module scope."
const __dirname = path.dirname(fileURLToPath(import.meta.url));
const AUTH_DIR = path.join(__dirname, ".auth");

const ROLE_CREDENTIALS = {
  admin: "admin@tenant1.test",
  engineer: "engineer@tenant1.test",
  analyst: "analyst@tenant1.test",
  auditor: "auditor@tenant1.test",
  readonly: "readonly@tenant1.test",
} as const;

const PASSWORD = "test-password-123";

for (const [role, username] of Object.entries(ROLE_CREDENTIALS)) {
  setup(`authenticate as ${role}`, async ({ page }) => {
    // keycloak.ts's onLoad: 'login-required' means any page load
    // without a valid session redirects here immediately -- no need
    // to click a separate "log in" button first.
    await page.goto("/");
    await page.waitForURL(/\/realms\/.+\/protocol\/openid-connect\/auth/, {
      timeout: 15_000,
    });

    // Keycloak's default login theme markup -- stable across recent
    // versions, but if this realm ever switches to a custom theme
    // these selectors are the first thing to check.
    await page.fill("#username", username);
    await page.fill("#password", PASSWORD);
    await page.click("#kc-login");

    // Back on the app, past the redirect. Wait for something that
    // only renders once keycloak-js has finished initializing and
    // AuthStore actually has a token, not just the URL changing --
    // navigation.spec.ts's own comments note the redirect landing is
    // not by itself proof the session is usable yet.
    await page.waitForURL((url) => !url.pathname.includes("/realms/"), {
      timeout: 15_000,
    });
    await expect(page.locator("body")).not.toContainText("Log in", {
      timeout: 15_000,
    });

    await page.context().storageState({
      path: path.join(AUTH_DIR, `${role}.json`),
    });
  });
}
