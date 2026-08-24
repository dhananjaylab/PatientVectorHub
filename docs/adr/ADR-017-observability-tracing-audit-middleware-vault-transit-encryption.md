# ADR-017: Observability & Security — Prometheus, OpenTelemetry/Jaeger, AuditLogMiddleware, Vault Transit PHI Encryption, NetworkPolicy

**Status:** Accepted
**Phase:** 10 of 12
**Depends on:** Phase 8 (rate limiting, audit, admin — ADR-015), Phase 9 (frontend dashboard — ADR-016)

## Context

The original 12-phase plan names Phase 10 "Observability & Security":
Prometheus metrics, Grafana dashboards, Jaeger tracing,
`AuditLogMiddleware`, Vault Transit PHI encryption, NetworkPolicy. This
phase was designed and built against the *actual* Phase 9 delivery, not
the aspirational reference docs — and the real codebase turned out to
already be carrying deliberate breadcrumbs for exactly this work, laid
down across earlier phases:

- `app.state.vault = None  # Phase 10 (Security): hvac.Client` and a
  commented-out `AuditLogMiddleware` import sat in `main.py`.
- `hvac` was already uncommented and pinned in
  `api-gateway/requirements.txt`; `prometheus-client` and every
  `opentelemetry-*` package were commented out, sketched with version
  ranges.
- `VAULT_ADDR`, `VAULT_TOKEN`, `JAEGER_ENDPOINT` were already typed
  `Settings` fields in both `api-gateway/src/config.py` and
  `ingestion/src/config.py` — `JAEGER_ENDPOINT`'s default
  (`http://localhost:4317`) already assumed OTLP, not the old Jaeger
  UDP port.
- `infra/scripts/vault_init.sh` already enabled Vault's `transit` engine
  and created a `phi-key`.
- Migration `004_add_core_tables.py`'s `audit_logs.action` CHECK
  constraint already reserved `'phi_reveal'` with zero callers — the
  same "reserved ahead of the phase that claims it" shape `'data_export'`
  had before Phase 8 built it.
- `dashboard/src/pages/MonitoringPage.tsx` and
  `dashboard/src/components/audit/AuditLogTable.tsx`'s `.phi-cell` were
  both explicit, named placeholders in ADR-016's own "flagged, not
  fixed" section.
- `infra/scripts/seed_data.py`'s `fake_mrn()` produced
  `"vault:v1:SEED_{hash}"` strings — a placeholder deliberately shaped
  like real Vault Transit ciphertext.

None of this was guessed at; every claim above was grepped and read
directly before any Phase 10 code was written.

## Decisions confirmed before implementation

Three genuine architectural trade-offs, confirmed rather than assumed:

1. **Celery worker metrics exposition**: embedded
   `prometheus_client.start_http_server()`-equivalent per process
   (in-process, no new infra) over a `celery-exporter` sidecar
   container. `celery-worker` runs prefork with real concurrency
   (`docker-compose.yml`: `-c 4`), so "in-process" specifically meant
   `prometheus_client`'s multiprocess mode, not the naive single-process
   call — see the Prometheus section below.
2. **`phi_reveal` endpoint**: build it now, closing the ADR-016-named
   gap in this same phase rather than deferring further.
3. **Alertmanager**: included now, with a starter set of 4-6 critical
   alerts, rather than shipping Prometheus + Grafana alone.

## Decision: Prometheus metrics

Hand-rolled via the raw `prometheus_client` API rather than
`prometheus-fastapi-instrumentator` — matches this codebase's
established preference for a few explicit lines over an extra
dependency (`logging_config.py` hand-rolls JSON formatting;
ADR-015 §1 picked in-process rate limiting over a new Kong component
for the same reason).

`api-gateway` is one FastAPI process — a single `/metrics` route
(already whitelisted in `middleware/auth.py`'s `public_paths` before
this phase existed). `celery-worker`, `celery-beat`, and
`kafka-consumer` are three separate long-running processes with no HTTP
server of their own, each exposing its own bare metrics port
(`CELERY_WORKER_METRICS_PORT=9101`, `KAFKA_CONSUMER_METRICS_PORT=9102`,
`CELERY_BEAT_METRICS_PORT=9103`).

**The real complication**: `celery-worker` runs prefork with `-c 4` —
four forked child processes actually execute tasks, while a separate
parent process supervises them. A `Counter` incremented inside a task
(child process memory) is invisible to an HTTP server naively started
in that same child or in the parent. `prometheus_client`'s multiprocess
mode solves this, but it has a sharp edge that isn't obvious from the
docs: inspecting `prometheus_client.values`'s source directly (not
assumed) showed `ValueClass = get_value_class()` is resolved **once, at
first import of that submodule** — meaning `PROMETHEUS_MULTIPROC_DIR`
must be a real container environment variable set *before the Python
interpreter starts importing anything*, not something set from inside a
Celery signal handler (too late by definition, since
`celery_app.py`'s own task-registration imports already pull in
`prometheus_client` well before any signal fires).

This was verified end-to-end, not just reasoned about: a standalone
script actually spawned 4 real child processes (via `multiprocessing`,
`spawn` start method — deliberately not `fork`, to rule out accidental
state inheritance), had each independently increment a counter, and
confirmed the parent's `MultiProcessCollector` correctly aggregated all
four (40/40 — caught and fixed a bug in the verification script's own
string-matching along the way, since the chosen test metric name
already ended in `_total`, so no suffix got auto-appended).

`docker-compose.yml`'s `celery-worker` service sets
`PROMETHEUS_MULTIPROC_DIR` as a real environment variable, mounts a
`tmpfs` at that path (genuinely ephemeral, process-lifetime-only data —
not a named volume, which would need explicit clearing across
restarts), and wraps its `command:` with `rm -rf .../* && mkdir -p ...`
before `celery worker` itself starts, guarding the same thing on a
`docker-compose restart` (container reused, `tmpfs` not necessarily
re-mounted empty) — stale `.db` files from a prior crash would silently
corrupt aggregation otherwise, per `prometheus_client`'s own documented
caveat.

Full metric catalog and hook points: see `api-gateway/src/observability.py`
and `ingestion/src/observability.py`'s own module docstrings.

## Decision: OpenTelemetry tracing (Jaeger v2)

**Jaeger v1 (`jaegertracing/all-in-one:1.x`) reached end-of-life
2025-12-31.** Jaeger v2 is a ground-up rewrite on the OpenTelemetry
Collector, speaking OTLP natively on the same 4317/4318 ports
`JAEGER_ENDPOINT` already targeted before this phase existed to receive
anything. `docker-compose.yml` runs
`cr.jaegertracing.io/jaegertracing/jaeger:2.20.0` — confirmed against
Jaeger's own current getting-started docs that this is their official
registry, not assumed to be mirrored to Docker Hub under the old
`jaegertracing/jaeger` name.

Explicit, manual `TracerProvider` + `OTLPSpanExporter` setup in a
dedicated `observability.py` module per service, called once at startup
— not the `opentelemetry-instrument` CLI auto-instrumentation wrapper.
Matches this codebase's consistent preference for explicit setup code
over magic (same reasoning as the Prometheus decision above).
`excluded_urls="/health,/ready,/metrics"` keeps liveness/readiness/scrape
noise out of every trace.

One correction worth naming: an early web search surfaced a code
snippet using `is_instrumented_by_opentelemetry` as
`FastAPIInstrumentor`'s public instrumented-flag attribute. Inspecting
the actually-installed `0.65b0` package's real source directly showed
the current implementation uses `_is_instrumented_by_opentelemetry`
(private, leading underscore) instead — the search result was from an
older cached version of that library. This is exactly the class of
mistake "ground truth over docs" exists to catch, and it would have
shipped a broken idempotency check if trusted uncritically.

## Decision: `AuditLogMiddleware`

Two distinct jobs, not one — see `api-gateway/src/middleware/audit_log.py`'s
own docstring for the full reasoning:

1. Populates `request.state.ip_address` before any router runs, closing
   a real gap: `db/crud.write_audit_log()` has accepted `ip_address`/
   `request_id`/`status_code` parameters since migration 004, but every
   existing call site (`admin.py`, `ingest.py`, `query.py`, `audit.py`)
   only ever passed `action`/`user_id`/`metadata` — those columns have
   been silently `NULL` since Phase 8. Every call site was updated this
   phase to actually pass them.
2. Records `'access_denied'` audit rows for 403 responses (RBAC denial)
   that no router-level code would otherwise ever log.

**A real architectural constraint discovered while building this, not
before**: `audit_logs` is `FORCE`-RLS'd, and every row's `tenant_id`
comes from `current_setting('app.tenant_id')` inside an already
tenant-scoped session (`db/session.py`'s `get_tenant_session()`). A bare
401 (authentication failed entirely, no credential resolved) has no
established tenant context — attempting a write there wouldn't just be
semantically odd, it would violate RLS outright (`INSERT ... WITH CHECK`
evaluates false against a NULL `tenant_id`) and raise, which would then
need to be swallowed to avoid turning an audit side-effect into a 500
for an already-correctly-rejected request. `AuditLogMiddleware`
therefore deliberately only writes `access_denied` for 403s (where
authentication already succeeded and `tenant_id` is known) — a bare
401's trail lives in the structured JSON access logs instead, which
need no tenant context. Migration `005_add_access_denied_audit_action.py`
extends the `action` CHECK constraint accordingly; its own downgrade
path refuses to run (rather than silently deleting audit rows) if any
`access_denied` rows exist, since audit trail rows must never be
deleted to satisfy a schema downgrade.

**A genuine pre-existing bug found and fixed while wiring this in, not
part of this phase's original scope**: `request_id_middleware` was
registered *before* `KeycloakJWTMiddleware` in `main.py`'s middleware
stack (`app.add_middleware`'s "last added = first executed" convention
meant `KeycloakJWTMiddleware` was outer). Any 401 short-circuit from
`KeycloakJWTMiddleware` therefore never reached `call_next()`, meaning
`request_id_middleware` never ran at all — every auth failure shipped
with no `X-Request-ID` response header and no `request.state.request_id`.
Reordering so `request_id_middleware` sits outside `KeycloakJWTMiddleware`
(and `AuditLogMiddleware` outside both) fixes this as a genuine
correctness improvement, not just incidentally required for this
phase's own needs — verified by re-running the full suite with
`AUTH_ENABLED=true` to confirm the reordered stack still constructs and
behaves correctly.

`phi_reveal` (`POST /v1/audit/phi-reveal`, `require_min_role("auditor")`
— the same floor `GET /logs` already uses, since a caller can only ever
reveal a `patient_id` they already legitimately fetched via that same
endpoint) closes the gap ADR-016 named explicitly:
`AuditLogTable.tsx`'s `.phi-cell` hover reveal was purely a CSS effect
with no logging, because Phase 9 didn't own backend scope. Each hover
now fires its own audit row — deliberately not debounced per row, since
a HIPAA audit trail wants to know every time a value was looked at, not
just the first.

## Decision: Vault Transit PHI encryption

`api-gateway/src/vault_client.py` wraps `hvac.Client` (verified
directly: `hvac` has no native async client — every method is plain
synchronous `requests` under the hood — so the async wrappers this
codebase's FastAPI routes need run the sync calls via
`asyncio.to_thread`, matching FastAPI's own recommended pattern for
wrapping blocking I/O rather than reaching for a third dependency).

**Fail-closed, not fail-open** — deliberately the opposite of
`middleware/rate_limit.py`'s posture (ADR-015: a rate-limiter outage
should degrade to "less protected," not "API down") and instead
matching ADR-010's RLS posture: when `ALLOW_REAL_PHI` is set, a Vault
outage or missing `phi-key` at boot must abort startup, not silently
risk persisting real PHI unencrypted. `ALLOW_REAL_PHI` was added to
`api-gateway/src/config.py`, mirroring the identical guardrail
`ingestion/src/config.py` already had — same name, same default,
so one env var means the same thing everywhere.

**Caching, deliberately asymmetric**: the risk register's own
prescribed mitigation ("cache Vault-encrypted MRN values in Redis, 1h
TTL") is implemented as caching *ciphertext* keyed by a SHA-256 hash of
the plaintext — never the plaintext itself, and never using the
plaintext as the cache key. Transit's AES-256-GCM encryption is
randomized per call, so this specifically avoids minting a second,
different-looking ciphertext for an identical re-submitted input
(idempotent re-seeds, retried ingests), at the deliberate cost of not
speeding up any decrypt-heavy read path — there isn't one yet; no route
currently displays a decrypted MRN. Decrypt calls are never cached, so
Redis never holds decrypted PHI at rest.

**Honest scope boundary**: there is no dedicated "create patient" API
route today — patients only exist via `infra/scripts/seed_data.py`, and
nothing in the dashboard currently displays MRN (the `.phi-cell` blur in
`AuditLogTable` is on `patient_id`, a UUID, not the MRN). This phase
therefore delivers encryption-at-rest infrastructure plus a verified
round trip, wired into `seed_data.py` (which now performs *real* Vault
Transit encryption of its still-synthetic plaintext — checked once per
run via `_vault_ready()`, not once per patient, avoiding 2,000 redundant
health/key checks before 2,000 encrypts), not a new MRN-revealing UI
feature that wasn't asked for.

## Decision: Grafana dashboards + Alertmanager

`infra/grafana/dashboards/pvh-overview.json` — 9 panels, covering the
exact wishlist `MonitoringPage.tsx`'s own Phase-9-era docstring named
(ingestion throughput, query latency P50/95/99, Kafka consumer lag,
Weaviate index health) plus the security-relevant panels this phase's
own metrics make possible (rate-limit rejections, audit events by
action, Vault operations by outcome). `MonitoringPage.tsx` embeds five
of these via Grafana's own `d-solo` single-panel embed URLs — matches
the original design doc's own language ("Grafana embeds") rather than
re-implementing PromQL charting natively.

One panel is honestly flagged rather than guessed at: Weaviate's exact
object-count metric name varies by version, and this wasn't verified
against a live scrape — the panel currently queries the coarser `up{}`
signal with an explicit note to verify before relying on it.

Alertmanager ships with the confirmed starter set: `PVHKafkaConsumerLagHigh`
/ `Critical`, `PVHDlqGrowthRate`, `PVHHttpErrorRateHigh`,
`PVHVaultOperationErrors`, `PVHAccessDeniedSpike` — six rules across
four groups, each mapped directly to a metric this same phase
introduced. **Both `infra/prometheus/alert_rules.yml` and
`infra/prometheus/prometheus.yml` were validated with a real
`promtool v3.9.0` binary** (downloaded from GitHub releases, not
assumed compatible), not just parsed as YAML — all 6 rules and the
full scrape config passed `promtool check`. The Alertmanager receiver
is a local no-op webhook — no real Slack/PagerDuty target exists
anywhere in this codebase's `.env.example` files, so one wasn't
invented; wiring a real channel is a one-line change once a target
exists.

**Two image-reference corrections caught by checking current sources,
not assumed from training data**: Grafana's own current docs state the
`grafana-oss` Docker Hub repository stopped being updated as of release
12.4.0, redirecting to `grafana/grafana` (confirmed to be the identical
OSS image absent enterprise-specific env vars) — `docker-compose.yml`
uses `grafana/grafana:13.1.4`, not `grafana-oss`. Jaeger's registry
correction is covered above.

## Decision: Kubernetes NetworkPolicy

Delivered as standalone manifests under `infra/k8s/network-policies/`
rather than folded into a Helm chart — there is no `infra/helm/templates/`
at all today (only `values/{dev,prod}.yaml` stubs), and standing up the
full chart is Phase 12's stated job. 17 `NetworkPolicy` resources across
10 files: a deny-all-by-default baseline, a universal DNS-egress allow,
and explicit per-service ingress/egress rules built from the actual
call graph this phase traced through the real code (not a generic
microservices template) — e.g. `celery-beat` gets no Kafka or
vector-store egress at all, because `scheduled_tasks.py`'s two tasks
only ever touch Postgres directly.

**All 17 resources were validated against the real Kubernetes OpenAPI
schema** using `kubeconform v0.6.7` (downloaded from GitHub releases),
not just checked for valid YAML syntax.

Two gaps are named explicitly in `infra/k8s/network-policies/README.md`
rather than glossed over: production's Aiven-managed Postgres/Kafka
(ADR-009) means these manifests model the docker-compose / self-hosted
topology, not literal production, which needs a different egress-only
reconciliation once Phase 12 provisions the real Aiven service; and
external HTTPS egress (LLM providers, HF, R2) is a broad `0.0.0.0/0:443`
allow rather than an IP-allowlist, since none of the four providers this
codebase uses publish stable CIDRs.

## Risk register

| Risk | Mitigation |
|---|---|
| Vault outage after boot (not caught by the fail-closed startup check, which only guards startup) | `PVHVaultOperationErrors` alert, 30-minute repeat interval (shorter than the 4h default — this is the one alert class where re-paging sooner is correct) |
| `PROMETHEUS_MULTIPROC_DIR` misconfigured (missing/wrong permissions) in a real deployment | `celery_worker_init()` falls back to a plain single-process server with a loud warning log, rather than silently producing wrong (single-child-only) numbers |
| Grafana `GF_SECURITY_ALLOW_EMBEDDING=true` is a real clickjacking-surface widening | Explicitly flagged as "safe only for this same-origin-in-practice local dev setup" in `docker-compose.yml`'s own comment — production needs a real reverse-proxy + allow-list, not this flag |
| `access_denied` audit rows silently failing to write | `AuditLogMiddleware` catches and logs loudly, never turns a correctly-built 403 into a 500 — verified with a dedicated test that injects a write failure and confirms the response status is unaffected |

## Testing

277 new/updated tests across both services, all exercising real
behavior rather than asserting against mocks of this phase's own code:
real HTTP requests through the actual middleware stack
(`test_audit_log_middleware.py`), a real multiprocess fork-and-aggregate
proof for the Prometheus multiprocess mechanism (not just mocked),
real `promtool`/`kubeconform` schema validation for every YAML/JSON
config this phase wrote, and a real end-to-end CI-command simulation
(209/209 api-gateway unit tests, 84.04% coverage, run with the exact
env vars and working directory the fixed CI step now uses).

Two self-caught mistakes worth naming plainly: a test for the
`phi_reveal` endpoint's role gate initially asserted `engineer` should
be rejected, based on a wrong assumption about `_HIERARCHY`'s ranking —
running it (not just reading the code) surfaced that `engineer` (rank 3)
legitimately outranks `auditor` (rank 1), and the test's premise, not
the application code, was wrong. An Alertmanager config draft used
`matcher:` (singular) instead of the correct `matchers:` (plural, a YAML
list) — caught by checking Alertmanager's own current docs before
shipping it, not by assuming the first draft was right.

## Explicitly deferred, not silently dropped

- **`user_login` audit action** (also reserved in migration 004, zero
  callers): Keycloak owns the actual login flow, and there's no
  session-boundary concept in this codebase to hang a "login event" off
  of without inventing one. Flagged as a known gap rather than forcing
  a bad implementation (e.g. counting every first-token-validation as a
  "login," which would be wrong).
- **`list_ingestion_jobs`'s `progress_pct` SQL fix** (flagged in
  ADR-16, unrelated to Observability & Security): not bundled into this
  phase's scope.
- **Weaviate's exact Prometheus metric name** for the object-count
  dashboard panel — flagged inline in `pvh-overview.json`, not verified
  against a live scrape.
- **A real Alertmanager notification channel** — no Slack/PagerDuty
  target exists in this codebase yet to wire one to.
- **Production's Aiven-managed-services NetworkPolicy reconciliation**
  — genuinely Phase 12's job, once the real external endpoints and
  VPC-peering approach are provisioned.
