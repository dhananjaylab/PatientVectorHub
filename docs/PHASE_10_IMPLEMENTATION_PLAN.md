# Phase 10 Implementation Plan: Observability & Security

**Depends on:** Phase 8 (ADR-015), Phase 9 (ADR-016)
**Delivers:** ADR-017

See ADR-017 for the full architectural reasoning, discovered bugs, and
explicitly-deferred items. This document is the practical
what-got-built / how-to-run-it companion.

## Running this locally

```bash
# 1. Bring up the full stack, including this phase's new services
docker-compose up -d postgres redis weaviate qdrant vault kafka keycloak \
  celery-worker celery-beat kafka-consumer \
  prometheus grafana jaeger alertmanager

# 2. One-time: create the Vault transit key (idempotent, safe to re-run)
./infra/scripts/vault_init.sh

# 3. Seed data -- now performs REAL Vault Transit encryption of
#    synthetic MRNs when Vault is reachable (falls back to a
#    placeholder with a warning if it isn't; refuses to run at all if
#    ALLOW_REAL_PHI=true and Vault genuinely isn't available)
python infra/scripts/seed_data.py

# 4. Run api-gateway on the host, as before (unchanged from Phase 9)
cd api-gateway && uvicorn src.main:create_app --factory --reload

# 5. New URLs
open http://localhost:9090        # Prometheus
open http://localhost:3001        # Grafana (admin / dev-only-not-for-prod)
open http://localhost:16686       # Jaeger UI
open http://localhost:9093        # Alertmanager
```

`dashboard/.env.local` needs `VITE_GRAFANA_URL=http://localhost:3001`
for `MonitoringPage.tsx`'s embeds to resolve (already added).

## File manifest

### api-gateway

| File | Change |
|---|---|
| `src/config.py` | New settings: `VAULT_TRANSIT_KEY`, `ALLOW_REAL_PHI`, `METRICS_ENABLED`, `TRACING_ENABLED`, `OTEL_SERVICE_NAME`, `PROMETHEUS_MULTIPROC_DIR`, `PHI_CACHE_TTL_SECONDS` |
| `requirements.txt` | Uncommented + pinned `hvac`, `prometheus-client`, `opentelemetry-*` (6 packages) — real versions verified via actual `pip install`, not guessed |
| `src/vault_client.py` | **New.** Vault Transit wrapper, fail-closed boot check, ciphertext-only Redis cache |
| `src/observability.py` | **New.** Prometheus registry (7 metrics) + OTel tracing setup, multiprocess-aware `/metrics` |
| `src/middleware/audit_log.py` | **New.** `AuditLogMiddleware` |
| `src/main.py` | Wired Vault, tracing, `/metrics` route, `AuditLogMiddleware`; **reordered middleware** (real bug fix, see ADR-017) |
| `src/db/session.py` | Added `get_engine()` accessor for OTel SQLAlchemy instrumentation |
| `src/db/crud.py` | `write_audit_log()` now increments `pvh_audit_log_writes_total` |
| `src/routers/admin.py`, `ingest.py`, `query.py`, `audit.py` | All `write_audit_log()` call sites now pass `ip_address`/`request_id`/`status_code`; `ingest.py` increments `pvh_documents_ingested_total`; `query.py` observes `pvh_query_latency_seconds` |
| `src/middleware/rate_limit.py` | Increments `pvh_rate_limit_rejections_total` (route template, not raw path) |
| `src/schemas/audit.py` | New `PhiRevealRequest` schema |
| `src/routers/audit.py` | New `POST /phi-reveal` endpoint |
| `migrations/versions/005_add_access_denied_audit_action.py` | **New.** Extends `audit_logs.action` CHECK constraint |
| `src/errors.py`, `tests/conftest.py` | **Reconstructed** — see `MANUAL_INTEGRATION_NOTES.md` |
| 6 new test files, 4 test files extended | See Test Results below |

### ingestion

| File | Change |
|---|---|
| `src/config.py` | New settings mirroring api-gateway's observability additions, plus per-service metrics ports |
| `requirements.txt` | Same 6 observability packages, verified installed together with existing celery/aiokafka/sqlalchemy pins |
| `src/observability.py` | **New.** Metrics + tracing, including the multiprocess-aware `celery_worker_init()`/`celery_worker_process_shutdown()` pair |
| `src/db/session.py` | Added `get_engine()` accessor |
| `src/workers/celery_app.py` | Wired `worker_init`/`worker_process_shutdown` signals |
| `src/workers/batch_worker.py` | Instrumented `process_document` (completed/failed counters, duration histogram) |
| `src/workers/dlq_producer.py` | Added `reason` parameter (low-cardinality), increments `pvh_dlq_messages_total` |
| `src/workers/stream_consumer.py` | Kafka consumer lag gauge (sampled every 50 dispatches), dispatch success/failure counters |
| `src/workers/scheduled_tasks.py` | Both tasks wrapped with a shared `_track_scheduled_task` context manager |
| 4 new test files | See Test Results below |

### infra / scripts / docker-compose / CI

| File | Change |
|---|---|
| `infra/scripts/seed_data.py` | Real Vault Transit MRN encryption, three-way fail-closed/fallback/real policy |
| `docker-compose.yml` | New services: `prometheus`, `grafana`, `jaeger`, `alertmanager`; updated `celery-worker`/`celery-beat`/`kafka-consumer`/`weaviate` |
| `infra/prometheus/prometheus.yml`, `alert_rules.yml` | **New.** Validated with real `promtool v3.9.0` |
| `infra/alertmanager/alertmanager.yml` | **New.** |
| `infra/grafana/provisioning/`, `infra/grafana/dashboards/pvh-overview.json` | **New.** 9-panel dashboard |
| `infra/k8s/network-policies/` (10 files) | **New.** 17 `NetworkPolicy` resources, validated with real `kubeconform v0.6.7` |
| `.github/workflows/ci.yml` | Vault service container + transit-key init step in `test-integration`; observability deps in both `test-unit` and `test-integration`; **fixed a real pre-existing bug** (`test-unit`'s missing `working-directory`, see ADR-017) |

### dashboard

| File | Change |
|---|---|
| `src/pages/MonitoringPage.tsx` | Real Grafana `d-solo` panel embeds, replacing the Phase 9 placeholder |
| `src/components/audit/AuditLogTable.tsx` | `.phi-cell` now fires `phi_reveal` on hover |
| `src/hooks/useAuditLogs.ts` | New `useLogPhiReveal` mutation; `access_denied` added to `AUDIT_ACTIONS` |
| `src/index.css` | New `.monitoring-*` classes; `.action-access_denied` |
| `.env.example`, `.env.local`, `src/vite-env.d.ts` | New `VITE_GRAFANA_URL` |
| `src/components/__tests__/AuditLogTable.test.tsx` | +4 tests for `phi_reveal` |

### Repo root

| File | Change |
|---|---|
| `MANUAL_INTEGRATION_NOTES.md` | **New.** Cross-service import mechanism + Phase 10 file-reconstruction notes |
| `docs/adr/ADR-017-*.md` | **New.** |

## Test results

| Suite | Result |
|---|---|
| api-gateway `pytest tests/unit` | **209/209 passing**, 84.04% coverage (gate: 60%) |
| ingestion `pytest tests/unit` | **68/68 passing** |
| dashboard `vitest run` | **52/52 passing** |
| dashboard `tsc -b` | Clean, 0 errors |
| dashboard `eslint . --max-warnings 0` | Clean |
| dashboard `npm run build` | Clean production build, 383KB JS (123KB gzipped) |
| `infra/prometheus/{prometheus,alert_rules}.yml` | Valid per real `promtool v3.9.0 check` |
| `infra/alertmanager/alertmanager.yml` | Valid YAML, correct `matchers:` syntax |
| `infra/k8s/network-policies/*.yaml` (17 resources) | Valid per real `kubeconform v0.6.7` against the Kubernetes OpenAPI schema |
| `infra/grafana/dashboards/pvh-overview.json` | Valid JSON, 9 panels, unique IDs |
| Full Phase 10 dependency set (both services) | Verified via real `pip install` — zero conflicts, `pip check` clean |

## For Phase 11 (Testing & Load Tests)

This phase's new metrics/tracing surfaces are natural load-test
assertions once Phase 11 stands up Locust: `pvh_kafka_consumer_lag`
staying bounded under sustained load, `pvh_documents_processed_total{status="failed"}`
staying near zero, `pvh_http_request_duration_seconds`'s p99 staying
under whatever SLO Phase 11 sets. The 80%-coverage ramp target
mentioned in the original 12-phase plan is unaffected by this phase —
api-gateway is already at 84.04%.

## For Phase 12 (Production Deployment)

- `infra/k8s/network-policies/` is ready to apply directly or fold into
  the Helm chart Phase 12 builds — see that directory's own `README.md`
  for the label-convention contract it assumes.
- The Aiven-managed Postgres/Kafka reconciliation (ADR-009) is
  unresolved — see ADR-017's risk register.
- Vault production auth: `config.py`'s existing comment
  (`# Production: VAULT_TOKEN unused — K8s ServiceAccount auth via Vault
  agent`) was already the plan before this phase; nothing here changes
  it, but implementing it is Phase 12's job once a real cluster exists.
- A real Alertmanager notification channel needs a real target to point
  at.
