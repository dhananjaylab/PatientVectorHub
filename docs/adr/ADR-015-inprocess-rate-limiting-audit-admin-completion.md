# ADR-015: In-Process Rate Limiting, Audit Router Completion, and Admin Namespace Health (Phase 8)

**Status:** Accepted
**Date:** Phase 8
**Deciders:** Engineering (rate-limiting architecture, audit export inclusion, and
admin namespace-health inclusion all confirmed with the product owner before
implementation — see "Decisions confirmed before implementation" below)

## Context

Phase 7 (ADR-014) shipped `/v1/query`. What was left of the original doc
06/09 "REST API & Kong Gateway" phase, cross-checked against the actual
repo rather than the aspirational docs:

- `routers/audit.py` didn't exist. `main.py` had a literal
  `# Phase 8+ routers` comment naming it specifically —
  `crud.write_audit_log`/`list_audit_logs` existed since Phase 4/6 with
  no HTTP caller until now.
- No rate limiting existed anywhere — no Kong, no in-process limiter,
  nothing, despite doc 09's full per-endpoint rate-limit table.
- `list_ingestion_jobs` was hardcoded to `LIMIT 100`, no `offset`, no
  total count — the only list endpoint in the codebase without real
  pagination (`list_audit_logs` already had both since Phase 4/6).
- The admin vector-store namespace health check
  (`GET /vector-store/namespaces` in doc 09) was never built in Phase
  3's `admin.py`.

Kong Gateway OSS was the original design's answer to rate limiting
(ADR-002, docs 07–12). It was never actually stood up anywhere in this
repo — no `docker-compose.yml` service, no k8s manifest, nothing;
it only ever existed in the aspirational docs. Kong OSS still needs its
own Postgres/Cassandra, a Redis instance for distributed rate limiting,
and a monitored data-plane cluster to run for real — exactly the kind of
self-hosted infrastructure weight ADR-009 moved this project away from
(EKS, Strimzi, CloudNativePG all got replaced by managed equivalents in
the actual build).

## Decisions confirmed before implementation

**1. Rate limiting: in-process (`slowapi` 0.1.10, Redis-backed), not Kong
Gateway OSS.** Reuses `REDIS_URL`, already shared by Celery's broker and
result backend — zero new infrastructure. Confirmed over Kong given the
above; confirmed over deferring rate limiting entirely given doc 09's
table has stood unimplemented since Phase 4/7 shipped the endpoints it
describes.

**2. Include a CSV/JSON audit-log export endpoint
(`GET /v1/audit/logs/export`).** `audit_logs.action` has carried the
`data_export` enum value since migration 004 with no caller until now;
doc 03's UI/UX brief describes export as part of the Audit Trail page.

**3. Include the admin vector-store namespace health endpoint
(`GET /v1/admin/vector-store/namespaces`).** In the original design docs,
never built in Phase 3.

## Decision

### 1. `slowapi` + Redis, decorator-per-route, not a blanket ASGI middleware

`@limiter.limit("N/minute")` is applied explicitly to each route that
doc 09's table lists a value for, matching how every other cross-cutting
guard in this codebase already works — `require_role()`/
`require_min_role()`/`get_db` are all declared per-route, never implied
by a global default. Anything not decorated is simply unlimited,
matching doc 09's own "—" cells (health/ready) rather than inventing a
blanket default rate.

Rate values applied, matching doc 09 where it specifies one, and a
documented judgment call where it doesn't:

| Route | Limit | Source |
|---|---|---|
| `POST /v1/ingest/jobs` | 100/min | doc 09 |
| `GET /v1/ingest/jobs/{id}` | 500/min | doc 09 |
| `GET /v1/ingest/jobs` (list) | 200/min | not in doc 09; matches the administrative-read default below |
| `POST /v1/query` | 1000/min | doc 09 |
| `GET /v1/audit/logs` | 200/min | doc 09 |
| `GET /v1/audit/logs/export` | 10/min | new endpoint; deliberately stricter — bulk read, heavier than a paginated list |
| `POST /v1/admin/api-keys` | 20/min | doc 09 |
| `DELETE /v1/admin/api-keys/{id}` | 20/min | doc 09 |
| `GET /v1/admin/api-keys`, `GET /v1/admin/users` | 200/min | not in doc 09; administrative-read default |
| `GET /v1/admin/vector-store/namespaces` | 200/min | doc 09 (exact) |
| `GET /health`, `GET /ready` | none | doc 09 ("—") — never decorated, so K8s liveness/readiness probes are never rate-limited |

### 2. Key function: caller identity, not raw IP

`rate_limit_key()` keys on `api_key_id` if present, else
`tenant_id:user_id`, else falls back to remote address (only reachable
with `AUTH_ENABLED=false` or an unauthenticated request that got this
far). IP-keying is wrong for this system specifically: many distinct
tenants can share one observed IP behind normal corporate NAT, so IP
buckets either dilute a shared-IP abuser's limit across innocent
neighbors or over-limit innocent users sharing an IP with someone else's
heavy usage. Keying on the identity `KeycloakJWTMiddleware` already
resolved makes each caller's quota genuinely their own.

### 3. Fail-open on the limiter's own backend trouble — the opposite of this codebase's RLS/auth posture, deliberately

`swallow_errors=True` + `in_memory_fallback_enabled=True`. Verified
directly: pointing `storage_uri` at an unreachable Redis with both flags
set does **not** disable enforcement outright — it falls back to
per-process in-memory counting, so a Redis outage degrades to
"per-instance limits instead of cluster-wide ones," not "no limits" and
not "API down." This is the opposite of ADR-010's fail-closed posture
for RLS/API-key auth, on purpose: rate limiting protects availability,
it doesn't gate access, so its own outage should degrade gracefully
rather than either blocking all traffic or removing protection outright
— mirrors the original design docs' own Kong rate-limit config,
which set `fault_tolerant: true # pass traffic if Redis unreachable`.

### 4. Custom 429 response, matching this codebase's error envelope

`slowapi`'s own default handler returns `{"detail": "..."}` (a bare
Starlette `HTTPException` shape). `rate_limit_exceeded_handler()`
instead produces `{"error": {"code": "RATE_LIMIT_EXCEEDED", "message",
"request_id", "retry_after_seconds"}}`, matching doc 09's example error
envelope and `errors.py`'s `PVHError`-derived shape used everywhere
else in this API.

### 5. Two library behaviors verified directly, not assumed — both would have silently broken the feature

Verified against the installed `slowapi==0.1.10` (wrapping `limits`),
not just its README:

- **Every route decorated with `@limiter.limit(...)` must declare both
  `request: Request` *and* `response: Response`** as explicit
  parameters. Without `response`, the decorator's header-injection step
  raises the instant the endpoint returns anything that isn't itself a
  raw `Response` object — which is every route in this codebase (all
  return Pydantic models, dicts, or `None`). `response: Response` is a
  standard FastAPI-injectable parameter; the decorator mutates its
  headers, and FastAPI merges them onto the real rendered response.
  Confirmed by reproducing the failure with a plain-dict-returning route
  missing `response`, then confirming it disappears once added.
- **The rate-limit bucket key incorporates the decorated function's bare
  `__name__` plus its `__module__`**
  (`f"{view_func.__module__}.{view_func.__name__}"`, read directly from
  `extension.py`), **not the route path**. Two different routes in the
  same module sharing a Python function name would silently share one
  bucket. Reproduced concretely while building this phase's test suite:
  two toy routes named `toy` in two different test functions bled into
  each other's limits despite different paths and different configured
  rates, until each was given a distinct name. Every real route handler
  in this codebase already has a distinct name within its own module, so
  this doesn't affect production behavior — it's recorded here, and in
  `middleware/rate_limit.py`'s own docstring, as a rule for future
  contributors: never reuse a route handler's function name elsewhere in
  the same module if it's going to carry this decorator.

Also confirmed, less surprising but worth stating: `Limiter()`
construction never blocks or raises on an unreachable `storage_uri` —
the connection is lazy, matching every other lazily-constructed client
in this codebase (OpenAI, Anthropic, Vault) — and `Response.headers` is
case-insensitive while `dict(response.headers)` is not, so the 429
handler reads `retry-after` directly off the `Headers` object rather
than a plain-dict copy (an earlier draft of the handler silently lost
this value by reading `"Retry-After"` off a `dict(...)` copy).

### 6. Test isolation: `limiter.enabled` toggled process-wide, not per-request-app

`middleware/rate_limit.py`'s `limiter` is a module-level singleton;
every route across `ingest.py`, `query.py`, `admin.py`, and `audit.py`
is decorated with it at import time, so its storage backend persists for
the lifetime of the pytest process, not per test or per constructed
test app. `tests/conftest.py` gained an autouse fixture that sets
`limiter.enabled = False` around every test by default (verified:
`enabled=False` fully bypasses checking without even incrementing the
underlying counter, and flipping back to `True` resumes counting from
whatever was already stored — so this has to be set for the whole run,
not toggled per test). `tests/unit/test_rate_limit.py` deliberately
re-enables the real flag around its own isolated toy routes to verify
actual enforcement, and restores `False` in a `finally`.

### 7. Audit router role model: a floor, not a strict allow-list, then self-scoping — matches doc 05's Role table exactly

`GET /v1/audit/logs` uses `require_min_role("auditor")` as the entry
floor (everyone except `readonly` passes — `auditor` is the *lowest*
non-readonly role in the hierarchy, so this is deliberately permissive
at the gate), then the handler forces non-admin/auditor callers to their
own `user_id` regardless of what they requested:

- **admin / auditor:** full tenant audit trail, any filter — matches
  doc 05's "auditor — Read-only on full audit_logs within tenant."
- **analyst / engineer:** their own actions only — matches doc 05's
  "analyst — Can read audit logs for own queries only," extended to
  engineers on the same reasoning (their own ingestion audit trail).
- **readonly:** blocked entirely (403 at the dependency).

An explicit attempt to filter by someone else's `user_id` is silently
overridden to the caller's own, not rejected with an error — matching
this codebase's existing precedent of filtering rather than erroring on
an unusable parameter value (e.g. `list_ingestion_jobs`'s `status`
filter), rather than surfacing a confusing permission error for what is,
from the caller's side, just a filter that doesn't apply to them.

`GET /v1/audit/logs/export` is a *stricter*, separate gate:
`require_role("admin", "auditor")` exact-match, no self-scoping
fallback. Bulk extraction of the full audit trail is compliance-evidence
territory (doc 01's "compliance officer... demonstrate HIPAA compliance
on demand" story), not a self-service feature for analysts/engineers to
pull their own history. Every export call writes its own `data_export`
audit_logs row — logged only after the underlying query succeeds, so a
failed export (e.g. a malformed date filter) is never itself recorded as
a completed export. Capped at 10,000 rows per export (`_EXPORT_ROW_CAP`)
— a genuinely larger pull is a case for direct DB access or a background
job, not a synchronous HTTP request; not solved here, just bounded so it
fails safely rather than hanging.

`list_audit_logs()` in `db/crud.py` gained `patient_id`/`from_ts`/
`to_ts` filters to match doc 03's UI/UX brief ("Full log filtered by
user, patient ID, time range, action type") — only `action`/`user_id`
were ever wired up before this phase.

### 8. Admin namespace health lives in `admin.py` but at a different RBAC bar than its file-mates

`GET /vector-store/namespaces` uses `require_min_role("engineer")`, not
`require_role("admin")` like every other route in `admin.py`. Doc 09
lists this route at "engineer+"; doc 03 lists the Vector Store page's
access level as "engineer+" too — engineers doing ingestion ops need to
check vector-store health as routine work, while API-key/user management
stays admin-only. `admin.py` is an organizational grouping of
admin-surface routes, not a uniform-permission boundary; RBAC is
declared per-route throughout this codebase, never implied by which file
a route lives in.

Imports `vector_store.interface.get_store` at module level, matching
`routers/query.py`'s precedent from Phase 7 (ADR-014) rather than an
earlier non-authoritative design sketch's local-import style. No new
Dockerfile or `sitecustomize.py` wiring needed — ADR-014 already made
`vector_store` resolvable from `api-gateway` (Dockerfile `COPY`s
`vector-store/src/` in, `sitecustomize.py` adds it to `sys.path` for
local dev, `conftest.py` aliases it for tests) when it added the
identical cross-package import for `rag_engine`'s reach into
`vector_store`.

### 9. `list_ingestion_jobs` gained real pagination, matching `list_audit_logs`'s existing shape

Was `list_ingestion_jobs(db, status=None) -> list[dict]`, hardcoded to
`LIMIT 100`, no `offset`, no total. Now
`list_ingestion_jobs(db, *, status=None, limit=50, offset=0) -> dict`,
returning `{"jobs": [...], "total": N}` — matching
`list_audit_logs`'s `{"logs": [...], "total": N}` shape exactly. The one
caller, `routers/ingest.py`'s `list_jobs`, gained `limit`/`offset` query
params (`ge=1, le=200` / `ge=0`, matching the audit endpoint's bounds)
and echoes `total`/`limit`/`offset` in its response envelope. No
`response_model` was ever declared on this route, so FastAPI's default
`jsonable_encoder` continues to handle the UUID/datetime fields inside
each job dict exactly as it always has.

## Consequences

- New dependency: `slowapi>=0.1.10,<0.2.0`. No new infrastructure — it
  reuses `REDIS_URL`.
- `admin.py`, `ingest.py`, and `query.py` each had zero or minimal prior
  unit test coverage (`admin.py` and `ingest.py` had *none* — no
  `test_admin.py`/`test_ingest.py` existed anywhere in the suite despite
  shipping in Phase 3/4). This phase adds `test_admin_router.py` and
  `test_ingest_router.py` from scratch, closing that gap, alongside the
  new `test_audit_router.py` and `test_rate_limit.py`. 135 tests total
  pass, including every pre-existing test file re-run unmodified as a
  regression check (`test_query_router.py`, `test_rbac.py`,
  `test_errors.py`, `test_phase1_health.py`) — none needed changes
  beyond what `conftest.py`'s new autouse fixture already covers.
- Carried forward from Phase 7 (ADR-014), still open, not addressed
  here: Qdrant DR mode has no keyword/BM25 signal; `api-gateway`'s
  image is heavier since it started depending on `rag-engine`/
  `vector-store`'s transitive dependencies.
- Kong Gateway remains undecided for a *production* deployment target —
  this ADR only settles the in-process approach for the application
  itself. If a future phase puts a real gateway in front of multiple
  API replicas (rather than in front of one process), that's a
  separate decision, not reversed by this one.

## References

- `docs/adr/ADR-009-aiven-openai-native-multitenancy-pivot.md`
- `docs/adr/ADR-010-api-key-auth-rls-bootstrap.md` (the fail-closed
  posture this ADR's rate-limiting fail-open posture deliberately
  contrasts with)
- `docs/adr/ADR-014-rag-query-engine.md`
- `docs/PHASE_8_IMPLEMENTATION_PLAN.md`
- slowapi source (`extension.py`, `wrappers.py`, `errors.py`,
  `util.py`) — read directly, not just its README, for every behavior
  cited above
- Docs 03 (App Flow — Audit Trail page, Vector Store page), 05 (Role
  table), 09 (API Contracts — rate-limit table)
