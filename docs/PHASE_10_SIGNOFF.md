# Phase 10 Signoff: Observability & Security

**Status: SIGNED OFF**, with two flagged gaps (non-blocking, listed in §6) and one
gap found and fixed during this signoff (§5).

This validates the Phase 10 code as actually integrated into the real repo —
not just what was originally delivered — including the subsequent login-crash
investigation and fix, and further work done after that fix was delivered.

## 1. What was validated

Three states were compared and reconciled:
- **Original Phase 10 delivery** (ADR-017, `PHASE_10_IMPLEMENTATION_PLAN.md`)
- **The login-loop fix** (`lib/keycloak.ts`'s circuit breaker, `App.tsx`'s error
  page and Retry-button fix, delivered in a follow-up turn)
- **This upload** — the real repo after integrating both, plus additional work
  done independently

## 2. Test results (this upload, as delivered)

| Suite | Result | Notes |
|---|---|---|
| api-gateway `pytest tests/unit` | **217/217 passing** | 8 more than original delivery — new `test_config.py` (2 tests) + pre-existing `test_auth_middleware.py` gained tenant-claim coverage (6 tests) for functionality that already existed |
| api-gateway coverage | **85.08%** (gate: 60%) | |
| api-gateway migration chain | `001 → 002 → 003 → 004 → 005 → 006`, resolves cleanly | New: `006_add_last_login_to_users.py` |
| ingestion `pytest tests/unit` | **68/68 passing** | Required restoring 4 test files dropped during integration — see §5 |
| dashboard `vitest run` | **64/64 passing** | |
| dashboard `tsc -b` | Clean, 0 errors | |
| dashboard `eslint . --max-warnings 0` | Clean | |
| dashboard `npm run build` | Clean production build | 389.78 kB JS (125.72 kB gzipped) |

All commands run exactly as CI runs them (matching env vars, working
directories, coverage flags) — not just "tests pass in isolation."

## 3. The original bug: two distinct root causes, both now fixed

The report was "keeps crashing while logging in and after logging in as
well." Investigation found **two separate, independent bugs** — one causing
the crash *during* login, one causing breakage *after* a successful login.
Both are now fixed and verified.

### 3a. Infinite redirect loop during login (`dashboard/src/lib/keycloak.ts`)

`keycloak-js`'s own `clearToken()` unconditionally calls `login()` again
whenever `onLoad: 'login-required'` is set, with no circuit breaker. Any
recurring cause of the post-redirect callback validation failing turns into
a genuine infinite loop. Confirmed by patching the actual, unmodified
`keycloak-js` v24.0.5 library with tracing and driving a real headless
browser through a full authorization-code+PKCE round trip.

**Fix**: a `sessionStorage`-backed attempt counter that stops calling
`keycloak.init()` after 3 failed round-trips, surfacing a clear error
instead of looping. Getting this right required a second pass — the first
version checked the counter on every call to `initKeycloak()`, but React
StrictMode double-invokes that effect, and the *first* invocation had
already triggered the real redirect (via `keycloak-js`'s own internal
`clearToken()` → `login()`) before the *second* invocation's throw could
matter. The fix gates the check behind the same `initPromise` singleton that
already coalesces concurrent init calls.

**Re-verified in this exact delivered code** (not just structurally): live
reproduction against a real browser + controlled OIDC stand-in, confirming
the loop now stops at exactly 4 redirect attempts with the correct
actionable error message rendered, both for a nonce-validation failure and
(observed as a bonus during this signoff) a CORS/network failure during
token exchange.

### 3b. Missing `tenant_id` claim after a successful login (`infra/keycloak/realm.json`)

**Found independently, after the loop fix was delivered — not something I
found originally.** The `tenant-id-claim` protocol mapper in
`infra/keycloak/realm.json` was a **top-level realm key**, which is not a
valid location for a client-scoped protocol mapper in Keycloak's schema —
it doesn't attach to any client. This means the `pvh-spa` client's issued
tokens **never actually included a `tenant_id` claim**, independent of and
in addition to the redirect-loop bug. `api-gateway/src/middleware/auth.py`
(pre-existing, unchanged in this phase) requires that claim and rejects
requests with `401 Missing or invalid tenant claim` when it's absent —
meaning even a login that completed successfully (didn't hit the loop)
would still leave every subsequent dashboard API call broken. This
precisely explains "...and after logging in as well."

**Fix**: the mapper moved to its correct location, nested inside the
`pvh-spa` client definition. A new `infra/keycloak/import_realm.py` script
also handles the operationally tricky part: Keycloak's `--import-realm`
startup flag skips realms that already exist, so simply fixing the JSON
file doesn't repair an already-imported realm — the script reconciles the
mapper on a *live* client via the Admin REST API (idempotent: checks
existing config, creates or updates only if needed).

**Verified**: `infra/keycloak/realm.json` now has zero top-level
`protocolMappers` key and the mapper is correctly nested under the
`pvh-spa` client (confirmed via direct JSON inspection). `import_realm.py`'s
logic was read in full and checks out — token acquisition, realm import
with graceful 409-already-exists handling, and the mapper reconciliation
(get-or-create-or-update) are all correctly implemented. Not independently
re-run against a live Keycloak in this sandbox (none available here) — this
is the one piece of §3 verified by code review rather than live
reproduction, flagged honestly rather than claimed as fully proven.

### Related hardening found alongside the above

- **`api-gateway/src/config.py`**: `KEYCLOAK_ISSUER`/`KEYCLOAK_JWKS_URL` are
  now *derived* from `KEYCLOAK_BASE_URL` + `KEYCLOAK_REALM` in the existing
  `model_post_init` hook, rather than independently hardcoded defaults. This
  directly addresses the class of bug where the Docker-mapped host port
  (8443) and a standalone Windows Keycloak (`start-dev`, port 8080) drift
  out of sync with each other. New `test_config.py` (2 tests) confirms both
  the derivation and that stale explicit overrides get normalized away.
  Verified: included in the 217/217 passing run above.

## 4. Everything else from the original Phase 10 delivery: unchanged, verified intact

A full file-by-file diff against my original delivery (post-login-fix
baseline) found **zero unintended changes** to any Phase 10 source file
except `lib/keycloak.ts` (§3a) — `App.tsx`, `AuditLogTable.tsx`,
`useAuditLogs.ts`, `MonitoringPage.tsx`, `observability.py` (both services),
`vault_client.py`, `middleware/audit_log.py`, the Prometheus/Grafana/
Alertmanager configs, and the Kubernetes NetworkPolicy manifests all carried
through byte-for-byte identical to what was originally delivered and
validated.

Minor, unrelated robustness fixes found in ingestion, all legitimate and
verified passing, none touching Phase 10's own logic:
- `kafka_config.py`: SSL certificate paths now resolve against the repo
  root (mirrors the same fix `config.py` already had for Kafka certs),
  handling Windows-style backslash paths too.
- `dlq_producer.py`: `publish_to_dlq_sync()` now detects whether it's being
  called from a context that already has a running event loop (e.g. some
  async test harnesses) and falls back to a dedicated thread rather than
  raising `asyncio.run() cannot be called from a running event loop`.
- `batch_worker.py`: the vector store client is now explicitly closed after
  `upsert()`, avoiding a connection leak — `test_admin_router.py`'s mocks
  were correctly updated to match (`mock_store.close = AsyncMock()`).

## 5. Gap found and fixed during this signoff

**Four test files were dropped during integration of the original Phase 10
delivery**, even though the source code they test made it in correctly:
`ingestion/tests/unit/test_observability.py`,
`ingestion/tests/unit/test_stream_consumer.py`,
`ingestion/tests/unit/test_scheduled_tasks.py`, and
`ingestion/tests/unit/test_ingestion_dlq.py` had reverted to a
pre-Phase-10 version (missing all metric-assertion tests and the
previously-absent success-path test for `process_document`). This meant
`ingestion/src/observability.py`'s Kafka-lag gauge, the multiprocess
aggregation logic, and `batch_worker.py`/`dlq_producer.py`'s metric
increments — all real, working code — had **zero test coverage** in what
was uploaded, despite being fully covered when originally delivered.

**Fixed**: all four files restored from the original delivery and
re-verified against the *current* source (not just re-added blindly) —
confirmed the restored `test_ingestion_dlq.py` still passes against the
current `dlq_producer.py`/`batch_worker.py`, which had themselves gained
the unrelated robustness fixes in §4 since original delivery. Full
68/68 result in §2 already reflects this restoration.

## 6. Remaining gaps — flagged, not silently fixed

- **`crud.touch_user_last_login()` is dead code.** The function, the
  `users.last_login` column (migration 006), and its exposure via
  `GET /v1/admin/users` are all correctly implemented, but nothing calls
  the function — confirmed by exhaustive grep across `src/` and `tests/`.
  The column will show `null` for every user forever until something calls
  it. The natural call site is `middleware/auth.py` on successful JWT
  validation, but that raises the same question ADR-017 already flagged for
  the deferred `user_login` audit action: should this update on *every*
  authenticated request (cheap but arguably not "login," just "active"), or
  only once per session (correct semantically, but this codebase has no
  session-boundary concept to hang that off of)? Left for an explicit
  decision rather than guessed at.
- **`infra/keycloak/import-realm.sh` and `import-realm.ps1` are stale**
  relative to `import_realm.py`. They implement only the basic
  import-or-skip-if-exists flow, *not* the tenant-id-claim mapper
  reconciliation §3b's fix depends on. Someone using either shell script
  instead of the Python one against an already-imported realm would
  reproduce the exact `tenant_id`-missing bug this signoff just confirmed
  fixed. `REALM_IMPORT_README.md` already steers toward `import_realm.py`
  as "the repo helper," which mitigates this, but the two incomplete
  scripts remaining in the repo is still a live trap for anyone who
  doesn't read the README closely.

## 7. Signoff

Phase 10 (Observability & Security) plus the subsequent login-crash
investigation and fix are **complete and verified** against the actual
delivered/integrated code: 217 + 68 + 64 = **349 tests passing**, clean
typecheck/lint/build, migration chain intact, and both root causes of the
original bug report independently confirmed fixed via live reproduction
(the redirect loop) and direct inspection (the missing tenant claim). The
two flagged gaps in §6 are pre-existing incompleteness in work done after
my original delivery, not regressions in anything Phase 10 itself
shipped, and don't block this signoff — they're operational/product
decisions for Dhananjay, not correctness bugs.
