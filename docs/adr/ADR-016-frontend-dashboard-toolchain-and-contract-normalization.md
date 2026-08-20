# ADR-016: Frontend Dashboard Toolchain, API-Contract Normalization, and Scope Boundaries (Phase 9)

**Status:** Accepted
**Date:** Phase 9
**Deciders:** Engineering (toolchain-major-version strategy, frontend test
coverage strategy, and styling approach all confirmed with the product
owner before implementation — see "Decisions confirmed before
implementation" below)

## Context

Phase 1's scaffold committed `dashboard/src/App.tsx`,
`hooks/useIngestionJobs.ts`, `hooks/useRAGQuery.ts`, and
`stores/useAuthStore.ts` with the comment "Full implementation added/wired
in Phase 9" on both hooks. Cross-checked against the actual repo rather
than the doc 03/09/35/40 sketches, three things were true before this
phase:

- `App.tsx` imported `{ initKeycloak, keycloak }` from `./lib/keycloak`
  and both hooks imported `{ api }` from `../lib/api` — **neither file
  existed**. Every dashboard dev-server/build invocation before this
  phase would have failed at module resolution before reaching a browser.
- `package.json` pinned React 18.3.1 / react-router-dom 6.24.0 /
  Vite 5.3.1 / TypeScript 5.5.2 / ESLint 8.57.0, all now well behind
  current. ESLint specifically was not just behind but **broken**: v8 has
  been EOL a long time, and v9 reached EOL on 2026-08-06 — the only
  currently-supported line, v10, only accepts flat config, and no
  `.eslintrc.*` ever existed in this repo for the old
  `eslint src/ --ext .ts,.tsx` lint script to resolve against in the
  first place.
- `@playwright/test` was a devDependency with a `test:e2e` script, but no
  `playwright.config.ts` existed — same broken-since-scaffold story.

Separately, verifying the real API surface this phase's hooks needed to
call against (not the doc 09/32 sketches) surfaced two live
inconsistencies worth designing around rather than working past:

- `GET /v1/ingest/jobs` (list) has no `response_model` — it returns
  `db/crud.py`'s `list_ingestion_jobs()` SELECT rows verbatim: `id`,
  `name`, `status`, `doc_count_total`, `doc_count_processed`,
  `doc_count_failed`, `created_at`. `GET /v1/ingest/jobs/{id}` and
  `POST /v1/ingest/jobs` go through `routers/ingest.py`'s
  `_to_response()`: `job_id`, `progress_pct`, `error_message`,
  `display_status` — **but no `name`**. The two endpoints describe "a
  job" with disjoint field sets; nothing in the codebase reconciled them
  before this phase.
- `schemas/query.py`'s `Citation` field is `document_type`, not `type`
  — the Phase 1 stub's TS type used `type`, which would have
  deserialized as `undefined` against the real response.
- `schemas/ingest.py`'s `IngestJobCreate` requires an explicit
  `documents: DocumentRef[]` (1–5000 items, each with `source_path` /
  `document_type` / `patient_id`) — not the single S3-prefix field doc
  03/32's sketches assumed.

## Decisions confirmed before implementation

**1. Toolchain majors: upgrade, not pin-and-patch.** React 19.2.8,
react-router 8.3.0, Vite 7.3.6 — confirmed over staying on the
already-pinned React 18/Router 6/Vite 5 majors, since this phase is
writing the app's routing and component code from scratch regardless (no
migration cost either way) and the person making the call wanted current
tooling, not a hedge toward the second-newest option.

**2. Frontend test coverage: both Vitest unit tests and new Playwright
e2e specs this phase.** Confirmed over shipping with e2e-only coverage
(deferring unit tests) or unit-only (deferring e2e) — package.json has
carried the Playwright dependency and script since Phase 1 with no
backing config, so e2e was already "owed"; Vitest/RTL had zero prior
footprint and needed setting up from nothing.

**3. Styling: keep the hand-rolled CSS design tokens already in
`index.css`, not Tailwind.** Confirmed over introducing Tailwind (which
the original TRD, doc 02, specified) — the Phase 1 scaffold's
`index.css` already encodes doc 04's dark-theme palette
(`--color-primary: #00B4D8`, IBM Plex fonts, 4px radii) as plain CSS
custom properties; migrating that to a utility-class system is a
cross-cutting rewrite orthogonal to wiring the dashboard's actual
functionality, which is what this phase is for.

## Decision

### 1. Toolchain versions — verified by real install, not assumed from search results

Every version below was confirmed by actually running `npm install` +
`tsc -b` + `eslint` + `vitest run` + `vite build` against this exact
combination in a sandbox before writing any application code — not
taken on faith from `npm view` or migration-guide text, both of which
turned out to be incomplete or wrong in specific ways (see the two
sub-decisions below).

| Package | Version | Note |
|---|---|---|
| react / react-dom | 19.2.8 | |
| react-router | 8.3.0 | replaces `react-router-dom`, which v8 removed entirely |
| @tanstack/react-query | 5.101.4 | same v5 API, minor bump |
| keycloak-js | 24.0.5 (`^24`, not `^26`) | pinned to match the Keycloak **server**'s major version (docker-compose pins `quay.io/keycloak/keycloak:24.0`); mixing a 26.x client against a 24.x server is a separate infra decision, not made here |
| zustand | 5.0.15 | |
| axios | 1.19.0 | |
| typescript | 5.9.3 (**not** 7.0.2) | see §2 below |
| vite | 7.3.6 | |
| @vitejs/plugin-react | 5.2.0 (**not** `^6`) | `^6` requires `vite ^8`; installing it against Vite 7 fails dependency resolution outright — caught by the real `npm install`, not discovered later |
| eslint | 10.8.1 | flat config only — see Context |
| typescript-eslint | 8.67.0 | |
| vitest / @testing-library/react | 4.1.10 / 16.3.2 | |
| @testing-library/dom | 10.4.1 | RTL 16's peer dependency — not previously in package.json anywhere; `npm install` would have resolved it transitively but pinning it explicitly documents that RTL needs it directly, not just via a subdependency |
| @playwright/test | 1.62.1 | |
| @types/node | 22.20.1 | needed for `playwright.config.ts`'s `process.env` access — Node types were never a dependency of a Vite-only frontend before this phase added a Node-context test-runner config |

### 2. TypeScript stays on 5.9, does not move to the new 7.0 native compiler

`npm view typescript version` resolves to `7.0.2` — the new Go-based
native-compiler line ("tsgo"), a real, current major release, not a
mistake in the registry. Installing it alongside `typescript-eslint@8.67`
and running `npm install` fails: `typescript-eslint` peer-depends on
`typescript@">=4.8.4 <6.1.0"`, so the wider TS ecosystem hasn't caught up
to TS7 yet. Verified directly rather than assumed — TypeScript 5.9.3 is
the actual version installed and typechecked against everything in this
phase.

### 3. `react-router`'s declarative API lives in the base package, not `react-router/dom`

The v8 migration notes describe removing `react-router-dom` in favor of
`react-router` **and** `react-router/dom`, phrased as though DOM-specific
APIs moved to the `/dom` subpath specifically. Verified directly against
the installed package: `react-router/dom` only exports `RouterProvider`,
`HydratedRouter`, and a couple of `unstable_*` RSC APIs — the
`data-router`/framework-mode surface this app doesn't use.
`BrowserRouter`, `Routes`, `Route`, `Navigate`, `Link`, `NavLink`,
`MemoryRouter`, `Outlet`, `useNavigate`, `useLocation`, `useParams`, and
`useSearchParams` — everything `App.tsx` and every page in this phase
uses — all ship from the main `react-router` entry point. Every import
in this phase's code reflects that verified reality, not the migration
guide's phrasing.

### 4. Normalizing the ingestion-job list/detail field mismatch

`hooks/useIngestionJobs.ts` defines two separate raw wire-shape
interfaces (`RawJobListRow`, `RawJobDetail`) and normalizes both into one
`IngestionJob*` shape rather than have components branch on which
endpoint a given job object came from. `components/ingestion/
JobProgressCard.tsx` is the component that actually reconciles them: it
takes the list-derived `initial` prop (has `name`, no live
`progress_pct`) and **merges** it field-by-field with each 2-second
`useJobDetail()` poll (has live `progress_pct`/`error_message`/
`display_status`, no `name`) via an explicit `mergeJobView()` function,
rather than replacing the object wholesale on each poll tick — a
wholesale-replace (`data ?? initial`, matching the original doc 35
sketch's own pattern) was written, tested, and observed to make the job
name disappear from every card the moment its first poll resolved.
`JobProgressCard.test.tsx`'s second test locks this in; reintroducing the
wholesale-replace pattern during this phase's work was confirmed to fail
that specific test before the merge fix was written, not assumed to.

An accompanying one-line backend fix — adding
`ROUND(doc_count_processed::numeric / GREATEST(doc_count_total,1) * 100,
1) AS progress_pct` to `list_ingestion_jobs`'s SELECT so the list
endpoint carries a real number instead of the frontend estimating it
client-side — was identified but **not made** in this phase; Phase 9 is
scoped to the frontend, and the client-side computation
(`computeProgressPct()`) is accurate enough between poll ticks that nothing
user-facing is broken by leaving it as a flagged follow-up rather than
a backend change bundled into a frontend phase.

### 5. Scope boundaries held deliberately, not discovered as gaps mid-build

- **Monitoring page is a placeholder.** No Prometheus/Grafana exists in
  this repo yet — that's the original 12-phase plan's Phase 10
  (Observability & Security). Rendering fabricated charts on a
  HIPAA-adjacent ops page would be actively misleading; the route,
  nav-guard, and RBAC floor (engineer+) are wired now so Phase 10 only
  has to fill in one component.
- **PHI-reveal hover stays purely visual.** `.phi-cell`'s CSS blur/hover
  toggle in `index.css` predates this phase; no new "log this reveal to
  audit_logs" API call was added, since Phase 8 didn't build such an
  endpoint and adding one is backend scope this phase doesn't own.
- **E2E coverage is readonly-only.** `AUTH_ENABLED=false`
  (`config.py`) means no `KeycloakJWTMiddleware` is mounted at all, and
  both `deps.py`'s `get_current_user()` and `middleware/rbac.py`'s
  `require_role()`/`require_min_role()` default an unset
  `request.state.role` to `"readonly"` — server-side, not just in the
  frontend's default `useAuthStore` state. This is real, current backend
  behavior verified this phase, not a frontend design choice: with auth
  disabled, **every** caller is treated as readonly, backend included.
  Playwright specs in `e2e/` are honest about this — they cover
  navigation, RBAC-driven 403s, and the (correctly empty, per the
  RBAC gates) dashboard a readonly visitor sees, and explicitly don't
  fabricate engineer/analyst/admin login flows that would need either
  real seeded Keycloak users (not present in `infra/keycloak/realm.json`
  as verified this phase) or a deliberate test-only auth bypass, neither
  of which this phase decided unilaterally to add.
- **CI does not run the Playwright suite.** e2e specs need the full
  `make dev` stack (Postgres/Redis/Keycloak/Kafka/Weaviate) running;
  wiring that into GitHub Actions is real CI infrastructure work of its
  own, not folded silently into this phase's CI change (see
  `docs/PHASE_9_IMPLEMENTATION_PLAN.md` §7). `.github/workflows/ci.yml`'s
  Phase 9 addition runs `npm run typecheck && npm run lint && npm run
  test && npm run build` — all backend-independent — and leaves e2e as
  a documented, deliberate gap.

## Consequences

- Node engine floor rises to **≥22.22.0** (`react-router@8`'s hard
  requirement, stricter than Vite 7's own `^20.19 || >=22.12`) —
  `.github/workflows/ci.yml`'s `actions/setup-node` moves from
  `node-version: "20"` to `"22"`.
- Anyone running `dashboard/` locally needs Node 22.22+; Node 20 will
  fail dependency installation outright, not just produce warnings.
- The list/detail normalization pattern in `useIngestionJobs.ts` is the
  template for any future endpoint pair that similarly returns
  different field sets for "the same resource" from different routes —
  normalize at the hook boundary, never let two wire shapes for one
  concept leak into component code.
