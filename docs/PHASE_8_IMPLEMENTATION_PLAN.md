# Phase 8 Implementation Plan — REST API Completion & Rate Limiting

Builds directly on Phase 7 (RAG Query Engine, ADR-014). Full architecture
reasoning lives in `docs/adr/ADR-015-inprocess-rate-limiting-audit-admin-completion.md`;
this document is the phase-level scope/sequencing record that ADR
references (`docs/PHASE_4_IMPLEMENTATION_PLAN.md` /
`docs/PHASE_6_IMPLEMENTATION_PLAN.md` style, per this repo's existing
convention).

## §1 Scope

Doc 06/09's original "REST API & Kong Gateway" phase is mostly already
done by Phase 7 — ingest/query/admin routers, `/health`+`/ready`, Swagger
auto-docs, `/v1` versioning all shipped in Phases 1–4/7. What was
genuinely still open, confirmed against the actual repo rather than the
aspirational docs:

1. Audit router (`GET /v1/audit/logs`, `GET /v1/audit/logs/export`) —
   `main.py` named this specifically in a `# Phase 8+ routers` comment.
2. Rate limiting — doc 09's per-endpoint table has been unimplemented
   since the endpoints it describes first shipped.
3. Admin vector-store namespace health (`GET /v1/admin/vector-store/namespaces`)
   — in the original design docs, never built in Phase 3.
4. Real offset pagination on the ingestion jobs list endpoint — the only
   list endpoint left with none.

Kong Gateway (ADR-002's original answer to rate limiting) explicitly
**not** built this phase — see ADR-015 §"Decisions confirmed before
implementation" for why, confirmed with the product owner before any
code was written.

## §2 Rate limiting (ADR-015 §1–6)

- `api-gateway/src/middleware/rate_limit.py` (new): `Limiter` singleton
  (`slowapi`, Redis-backed via the existing `REDIS_URL`), `rate_limit_key()`
  (caller-identity keying, not IP), custom `rate_limit_exceeded_handler()`
  matching this codebase's error envelope.
- `api-gateway/src/config.py`: `RATE_LIMIT_ENABLED: bool = True` added.
- `api-gateway/src/main.py`: `app.state.limiter = limiter`,
  `RateLimitExceeded` exception handler registered.
- Every route in `ingest.py`, `query.py`, `admin.py` (existing routes)
  and `audit.py` (new) gained `request: Request` + `response: Response`
  params (where missing) and a `@limiter.limit(...)` decorator matching
  doc 09's table (full mapping in ADR-015 §1).
- `api-gateway/requirements.txt`: `slowapi>=0.1.10,<0.2.0` added. No
  other new dependencies — the Redis storage backend works against the
  `redis` package already pinned.

## §3 Audit router (ADR-015 §7)

- `api-gateway/src/schemas/audit.py` (new): `AuditLogEntry`,
  `AuditLogListResponse`.
- `api-gateway/src/routers/audit.py` (new): `GET /logs` (list +
  filters + pagination, role-floor + self-scoping), `GET /logs/export`
  (CSV/JSON, admin/auditor only, writes its own `data_export` audit
  entry).
- `api-gateway/src/db/crud.py`: `list_audit_logs()` extended with
  `patient_id`/`from_ts`/`to_ts` filters (doc 03's UI/UX brief describes
  all four filter dimensions; only two were ever wired up before this
  phase).
- Mounted in `main.py` at `/v1/audit`, replacing the file's own
  `# Phase 8+ routers` placeholder comment.

## §4 Admin namespace health (ADR-015 §8)

- `api-gateway/src/schemas/admin.py`: `NamespaceHealthResponse` added.
- `api-gateway/src/routers/admin.py`: `GET /vector-store/namespaces`
  added, `require_min_role("engineer")` (a different, lower bar than
  this file's other `require_role("admin")` routes — intentional, see
  ADR-015). Imports `vector_store.interface.get_store` at module level,
  reusing Phase 7's already-solved cross-package wiring — no Dockerfile
  changes needed.

## §5 Pagination completion (ADR-015 §9)

- `api-gateway/src/db/crud.py`: `list_ingestion_jobs()` changed from
  `(db, status=None) -> list[dict]` (hardcoded `LIMIT 100`, no offset,
  no total) to `(db, *, status=None, limit=50, offset=0) -> dict`
  returning `{"jobs": [...], "total": N}`, matching `list_audit_logs`'s
  existing shape.
- `api-gateway/src/routers/ingest.py`: `list_jobs` gained `limit`/
  `offset` query params (`ge=1, le=200` / `ge=0`) and echoes
  `total`/`limit`/`offset` in its response.

## §6 Testing

New files:
- `tests/unit/test_rate_limit.py` — key-derivation logic, real
  enforcement (429 + envelope shape) via an isolated toy app, config
  assertions (fail-open flags, shared Redis URL).
- `tests/unit/test_audit_router.py` — role-floor + self-scoping matrix,
  filter pass-through, CSV/JSON export (including the zero-row and
  metadata-recording cases), 422s on bad pagination/format values.
- `tests/unit/test_admin_router.py` — **new coverage for a
  previously-untested router** (no `test_admin.py` existed before this
  phase despite `create_key`/`revoke_key`/`list_keys`/`get_users`
  shipping in Phase 3): full RBAC matrix on all five routes, response
  serialization, the new namespace-health endpoint's different RBAC
  bar.
- `tests/unit/test_ingest_router.py` — **new coverage for a
  previously-untested router** (`get_job`/`list_jobs` had none;
  `create_job` had none despite shipping in Phase 4): Kafka publish
  fan-out (one message per document), audit logging, pagination
  parameters, 404/403/422 paths.

Modified:
- `tests/conftest.py` — autouse fixture disabling the process-wide
  `limiter` singleton for every test by default (see ADR-015 §6 for why
  this has to be session-safe, not per-test-app).

Regression-verified (unmodified, re-run against Phase 8's code):
`test_query_router.py`, `test_rbac.py`, `test_errors.py`,
`test_phase1_health.py`. **135 tests total pass** — every pre-existing
file plus all new coverage, zero changes needed to the pre-existing
files beyond the shared `conftest.py` fixture.

Two library behaviors were verified directly against the installed
`slowapi==0.1.10` source before being relied on in code — see ADR-015 §5
for both (the `response: Response` parameter requirement, and the
`{module}.{function_name}` bucket-key scoping) — this is not a "trust
the docs" integration; it's read-the-source-and-reproduce-it, matching
this project's standard for every other third-party library integrated
so far (`AIOKafkaProducer`, `AsyncOpenAI`, `weaviate-client`, etc.).

## §7 Done criteria

- [x] `GET /v1/audit/logs` returns role-appropriate results with
      action/user/patient/time-range filters and real pagination.
- [x] `GET /v1/audit/logs/export` returns CSV or JSON, admin/auditor
      only, and records its own `data_export` audit entry.
- [x] `GET /v1/admin/vector-store/namespaces` returns tenant/backend/
      health status, engineer+.
- [x] Every route doc 09 lists a rate limit for enforces that limit;
      `/health`/`/ready` remain unlimited.
- [x] 429 responses match this codebase's standard error envelope with
      a numeric `retry_after_seconds` and standard rate-limit headers.
- [x] `GET /v1/ingest/jobs` supports real `limit`/`offset` with a total
      count.
- [x] All new code has unit test coverage; all pre-existing tests still
      pass unmodified.
- [x] No new infrastructure — `slowapi` reuses the existing Redis
      instance.

## §8 Carried forward, not addressed this phase

- Qdrant DR mode still has no keyword/BM25 signal (Phase 6/7, ADR-013/014).
- `api-gateway`'s container image is heavier since Phase 7 pulled in
  `rag-engine`/`vector-store`'s transitive dependencies — not revisited.
- Kong Gateway (or any reverse-proxy-level gateway) for a genuinely
  multi-replica production deployment is still an open question — this
  phase settled in-process rate limiting for the application itself,
  not the production topology question.
- `config.py`'s pre-existing `SyntaxWarning: invalid escape sequence '\c'`
  (a literal `certs\ca.pem` example inside a docstring) is unrelated to
  this phase's changes and was left as-is rather than drive-by-fixed
  outside the phase's stated scope.
