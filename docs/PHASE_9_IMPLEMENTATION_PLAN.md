# Phase 9 Implementation Plan: Frontend Dashboard

**Status:** Complete
**Builds on:** Phase 8 (ADR-015 — rate limiting, audit router, admin
namespace health), merged and validated.
**Governing ADR:** [ADR-016](adr/ADR-016-frontend-dashboard-toolchain-and-contract-normalization.md)

## 1. Goal

Replace `dashboard/`'s Phase 1 scaffold — a route skeleton with two
type-only stub hooks, both literally commented "Full implementation
added/wired in Phase 9" — with a working dashboard covering every page
doc 03's App Flow describes access levels for, wired against the real
Phase 3–8 API surface rather than the aspirational doc 09/32/35 sketches.

## 2. Scope confirmed before implementation

Three decisions were confirmed with the product owner before writing
code (see ADR-016 §"Decisions confirmed before implementation" for full
reasoning):

1. Toolchain majors: upgrade to React 19 / react-router 8 / Vite 7,
   not stay on the Phase-1-pinned React 18 / Router 6 / Vite 5.
2. Frontend test coverage: both Vitest unit tests and new Playwright
   e2e specs this phase, not one or the other.
3. Styling: keep the hand-rolled CSS tokens in `index.css`, not
   introduce Tailwind.

Two smaller decisions were made without a separate confirmation round
and flagged as defaults up front, before code was written: the
Monitoring page ships as an honest placeholder (no Prometheus/Grafana
exists yet — that's the original plan's Phase 10), and PHI-reveal hover
stays purely visual (no new "log this reveal" API call, since Phase 8
never built one).

## 3. Files added / changed

### Config & tooling
| File | Change |
|---|---|
| `package.json` | Rewritten — see ADR-016 §1 for exact versions |
| `eslint.config.js` | New — flat config (none existed before) |
| `tsconfig.json` | Updated — ES2022, project references |
| `tsconfig.node.json` | Updated — covers `vite.config.ts`, `playwright.config.ts`, `e2e/**/*.ts`; uses `emitDeclarationOnly` not `noEmit` (see §6) |
| `vite.config.ts` | Updated — dev proxy unchanged, Vitest config merged in |
| `playwright.config.ts` | New — package.json had the dependency and script since Phase 1 with no config to back them |
| `.env.example` | New — `VITE_*` client env vars, separate from the repo-root `.env.example` |
| `src/vite-env.d.ts` | New — typed `ImportMetaEnv` |

### Fixing the broken imports
| File | Change |
|---|---|
| `src/lib/keycloak.ts` | New — `App.tsx` has imported this since Phase 1; never existed |
| `src/lib/api.ts` | New — both original hooks have imported this since Phase 1; never existed |
| `src/lib/rbac.ts` | New — extracted shared `ROLE_HIERARCHY` (was inline in `App.tsx`) |

### State & data
| File | Change |
|---|---|
| `src/stores/useAuthStore.ts` | Tightened `role`'s type to the shared `Role` union |
| `src/hooks/useIngestionJobs.ts` | Rewritten — normalizes the list/detail field mismatch, see ADR-016 §4 |
| `src/hooks/useRAGQuery.ts` | Rewritten — trimmed to the real `QueryFilters`/`Citation` shape |
| `src/hooks/useAuditLogs.ts` | New |
| `src/hooks/useAdmin.ts` | New — API keys, users, namespace health |

### Components
`components/common/{StatusBadge,Pagination,RoleGuard}.tsx`,
`components/layout/AppLayout.tsx`,
`components/ingestion/{JobProgressCard,NewJobForm}.tsx`,
`components/query/{QueryForm,QueryResultCard}.tsx`,
`components/audit/AuditLogTable.tsx` — all new.

### Pages
`pages/{DashboardPage,IngestionPage,NewJobPage,QueryPage,AuditLogPage,
MonitoringPage,NotFoundPage}.tsx`,
`pages/admin/{AdminLayout,AdminApiKeysPage,AdminUsersPage,
AdminNamespacesPage}.tsx` — all new.

### App shell
`src/App.tsx` — full rewrite; `src/main.tsx` — named `StrictMode`
import (React 19's automatic JSX runtime doesn't need a default `React`
import just to reference it).

### Styling
`src/index.css` — Phase 1's token set (`--color-primary` etc.) kept
verbatim; every class referenced by a Phase 9 component appended.

### Tests
`src/test/{setup.ts,testUtils.tsx}`,
`src/lib/__tests__/{rbac,api}.test.ts`,
`src/hooks/__tests__/{useIngestionJobs,useRAGQuery}.test.tsx`,
`src/components/__tests__/{JobProgressCard,Pagination,AuditLogTable}.test.tsx`,
`src/App.test.tsx`,
`e2e/{navigation,dashboard}.spec.ts` — all new.

### CI
`.github/workflows/ci.yml` — Node 20→22, new dashboard job (§7).

## 4. API-contract findings (see ADR-016 §"Context" and §4 for full detail)

Three real divergences between the doc sketches / Phase 1 stub types and
the actual shipped API were found and designed around, not discovered as
runtime bugs later:

1. `GET /v1/ingest/jobs` (list) and `GET /v1/ingest/jobs/{id}` (detail)
   return different field sets for "a job." Normalized at the hook
   boundary; `JobProgressCard` merges rather than replaces so the job
   name survives past the first detail poll (regression-tested, see §5).
2. `Citation.document_type`, not `Citation.type`.
3. `IngestJobCreate` needs an explicit `documents[]` array
   (`source_path`/`document_type`/`patient_id` per item), not a single
   S3-prefix field — `NewJobForm.tsx` offers manual repeatable rows plus
   a "paste JSON" bulk-entry mode for this reason.

## 5. Testing

### Unit (Vitest + React Testing Library) — 48 tests, 8 files, all passing
- `lib/rbac.test.ts` (9) — hierarchy values match
  `middleware/rbac.py`'s `_HIERARCHY` exactly; exact-vs-min-role
  distinction.
- `lib/api.test.ts` (10) — error-envelope parsing against the real
  `{ error: {...} }` shape from `middleware/rate_limit.py`.
- `hooks/useIngestionJobs.test.tsx` (4) — list/detail normalization,
  zero-division guard.
- `hooks/useRAGQuery.test.tsx` (2) — `document_type` field, omitted
  `llm_provider`.
- `components/JobProgressCard.test.tsx` (3) — **the regression test**:
  confirmed to fail when the wholesale-replace pattern (`data ?? initial`)
  was reintroduced, confirmed to pass again once reverted to the merge
  — this was verified by actually breaking and re-fixing the component
  mid-phase, not asserted from reading the code.
- `components/Pagination.test.tsx` (5), `components/AuditLogTable.test.tsx`
  (5) — role-gated control visibility, PHI blur class, offset math.
- `App.test.tsx` (10) — every route guard combination in `App.tsx`,
  including the exact-vs-min-role distinction between `/admin` (engineer+)
  and `/admin/api-keys` (admin-only).

Global `clearMocks: true` was added to `vite.config.ts`'s test config
after a real cross-test-pollution failure: `useJobDetail`'s
"does not fire when jobId is undefined" test was failing because it saw
call counts left over from earlier tests sharing the same
`vi.mock('../../lib/api')` module instance, not because the `enabled:
false` guard was actually broken. Fixed once, globally, rather than
adding `beforeEach(vi.clearAllMocks)` to every test file individually.

### E2E (Playwright) — 2 spec files, readonly-role coverage only
`AUTH_ENABLED=false` means every caller — frontend and **backend** — is
treated as `readonly` (verified against `deps.py`/`middleware/rbac.py`
directly, not assumed). `e2e/navigation.spec.ts` and
`e2e/dashboard.spec.ts` cover what's honestly testable under that
constraint: routing, RBAC-driven 403s, nav-link visibility, 404 handling,
and the (correctly empty) dashboard a readonly visitor sees. Extending
coverage to engineer/analyst/auditor/admin flows needs either real seeded
Keycloak users per role (not present in `infra/keycloak/realm.json` as of
this phase) or a deliberate test-only auth bypass — flagged as a
follow-up (§7), not decided unilaterally here.

Playwright browser binaries could not be installed in the verification
sandbox this phase was built in (`playwright install` needs
`deb.nodesource.com`, outside that sandbox's network allowlist) — the
specs are written and typecheck/lint cleanly, but have not been executed
against a live browser. Run `npx playwright install && npm run test:e2e`
locally (with `make dev` running) before relying on them for the first
time.

## 6. A real TypeScript project-references error hit and fixed

`tsc -b` initially failed with `TS6310: Referenced project
'tsconfig.node.json' may not disable emit` — caused by combining
`composite: true` with `noEmit: true` in a project that's the *target*
of another project's `references`. TypeScript's project-reference build
mode requires a referenced project to actually emit something (its
`.d.ts` output is what makes it "referenceable" at all); `noEmit: true`
categorically breaks that regardless of how the build is invoked.
Fixed by switching `tsconfig.node.json` to `emitDeclarationOnly: true`
with `outDir` pointed at a gitignored `node_modules/.tmp/` path — emits
just the declaration files project references need, nothing that
clutters the source tree. Confirmed by reproducing the failure and then
the fix, not fixed speculatively.

## 7. Deferred / follow-up work (not done in this phase, flagged not silently skipped)

- **Add `progress_pct` to `list_ingestion_jobs`'s SELECT.** A one-line
  backend change (`ROUND(doc_count_processed::numeric /
  GREATEST(doc_count_total,1) * 100, 1) AS progress_pct`) that would let
  the list endpoint carry a real number instead of the frontend
  estimating it client-side. Not made here — Phase 9 is scoped to the
  frontend, and the client-side estimate is accurate enough between poll
  ticks.
- **CI e2e job.** Needs the full `make dev` stack running in GitHub
  Actions (Postgres/Redis/Keycloak/Kafka/Weaviate) — real infrastructure
  work, not bundled into this phase's CI change.
- **Role-diverse e2e coverage.** Needs a decision on seeded Keycloak test
  users vs. a test-only auth bypass — a product/security decision, not
  made unilaterally here.
- **Manifest-file upload for bulk ingestion.** `NewJobForm.tsx`'s
  "paste JSON" mode covers the bulk-entry need for now;
  `schemas/ingest.py`'s own docstring already flagged a real upload
  endpoint as a "Phase 4+ enhancement, not blocking," and it still isn't
  built.
- **Observability & Security phase (original plan's Phase 10).**
  `MonitoringPage.tsx` is an intentional placeholder until Prometheus/
  Grafana actually exist.

## 8. Running this locally

```bash
cd dashboard
cp .env.example .env.local
npm install
npm run dev          # http://localhost:5173, proxies /v1 -> localhost:8000
npm run typecheck
npm run lint
npm run test          # Vitest, no backend needed
npm run build
npx playwright install && npm run test:e2e   # needs `make dev` running first
```
