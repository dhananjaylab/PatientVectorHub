# Phase 11 Implementation Plan: Testing & Load Tests

**Depends on:** Phase 9 (ADR-016), Phase 10 (ADR-017)
**Delivers:** ADR-018

See ADR-018 for the full architectural reasoning, discovered bugs, and
explicitly-deferred items. This document is the practical
what-got-built / how-to-run-it companion — and, because this phase
spans more work than one session, the living status tracker for it.

## Status

| Stage | Scope | Status |
|---|---|---|
| 11.0 | CI test matrix: fix the broken `test-integration` step, wire CI for all 6 services, relocate/fix misplaced tests | ✅ Implemented |
| 11.1 | Coverage gate ramp (real baselines → enforced `--cov-fail-under`) | ✅ Implemented |
| 11.2 | Locust load-test harness | 🔜 Designed (ADR-018), not yet built |
| 11.3 | Playwright RBAC E2E | 🔜 Designed (ADR-018), not yet built |
| 11.4 | Adversarial security suite / RLS pen test | 🔜 Designed (ADR-018), not yet built |
| 11.5 | Presidio PHI leak scanner | 🔜 Designed (ADR-018), not yet built |

## Running this locally (Stages 11.0 / 11.1)

```bash
# Each backend service's suite now installs and runs the same way CI
# does -- no infra needed for the unit-test layer.
cd api-gateway && pip install -r requirements.txt \
  && pytest tests/unit/ --cov=src --cov-fail-under=80

cd ingestion && pip install -r requirements.txt \
  && pytest tests/unit/ --cov=src --cov-fail-under=65

cd vector-store && pip install -r requirements.txt \
  && pytest tests/unit/ --cov=src --cov-fail-under=80

cd rag-engine && pip install -r requirements.txt \
  && pytest tests/unit/ --cov=src --cov-fail-under=80

cd embedding-server && pip install pytest pytest-cov huggingface_hub python-dotenv \
  && pytest tests/unit/

# Integration tests need the full local stack up first (unchanged from
# Phase 10), then run per-service -- the same four working directories
# the fixed CI job now uses:
docker-compose up -d postgres redis kafka weaviate qdrant vault
for svc in api-gateway ingestion vector-store rag-engine; do
  (cd "$svc" && pytest tests/integration/ -m integration -v)
done
```

## File manifest

### `.github/workflows/ci.yml`

| Change | Detail |
|---|---|
| **Fixed** `test-integration`'s final step | Was one step, no `working-directory`, targeting a `tests/integration/` path that doesn't exist anywhere in the repo — reproduced the collection failure before fixing. Now 4 steps, one per service (`api-gateway`, `ingestion`, `vector-store`, `rag-engine`), each `cd`-scoped the same way the existing Alembic step already is. |
| **New** `test-unit-ingestion` job | Never existed. 54/54 passing, 68% coverage, gate at 65% (ramping to 80% — see "Remaining work" below). |
| **New** `test-unit-vector-store` job | Never existed. 30/30 passing, 89% coverage, gate at 80%. |
| **New** `test-unit-rag-engine` job | Never existed. 30/30 passing, 92% coverage, gate at 80%. |
| **New** `test-unit-embedding-server` job | Never existed. 1/1 passing, not coverage-gated (scripts/, not src/ — see ADR-018). |
| **Updated** `security-scan`'s `needs:` | Now requires all 4 new jobs pass, not just `lint`/`test-unit`. |

### `ingestion/`

| File | Change |
|---|---|
| `requirements.txt` | **Fixed.** Added `qdrant-client>=1.18.0,<1.19.0` (missing — `conftest.py`'s cross-package alias to `vector_store` needs it; a clean install previously failed collection for every test in the service) and `pytest-cov>=5.0.0,<6.0.0`. |
| `tests/unit/test_clinical_bert_embedder.py` | **New here** (relocated from `embedding-server/tests/unit/` — see ADR-018). 13 tests, now passing; `src/embeddings/clinical_bert_embedder.py` goes from 0% to 100% covered. |

### `vector-store/`

| File | Change |
|---|---|
| `requirements.txt` | **Fixed.** Added `pytest>=8.0.0,<9.0.0`, `pytest-asyncio>=0.24.0,<0.25.0` (missing entirely — `pytest.ini` requires it, 3 of 7 unit test files use async tests, a clean install couldn't collect them), `pytest-cov>=5.0.0,<6.0.0`. |

### `rag-engine/`

| File | Change |
|---|---|
| `requirements.txt` | Added `pytest-cov>=5.0.0,<6.0.0` (only gap found here — suite was otherwise clean). |

### `api-gateway/`

| File | Change |
|---|---|
| `tests/unit/test_logging_config.py` | **New here** (relocated + fixed from `embedding-server/tests/unit/test_logging.py` — see ADR-018). Also fixed a second, independent bug in the file itself: missing `import logging` and `import json`. 11 tests, now passing; `src/logging_config.py` goes from untested to 96% covered. |

### `embedding-server/`

| File | Change |
|---|---|
| `tests/unit/test_clinical_bert_embedder.py`, `tests/unit/test_logging.py` | **Removed** — relocated to their correct services (see above). Neither ever tested anything embedding-server actually owns. |

### Repo root

| File | Change |
|---|---|
| `docs/adr/ADR-018-*.md` | **New.** |

## Test results (Stages 11.0 / 11.1)

| Suite | Result |
|---|---|
| api-gateway `pytest tests/unit` | **228/228 passing**, 85% coverage (gate: 80%) — up from 209/209 at 84.04% before this phase's relocated logging test |
| ingestion `pytest tests/unit` | **54/54 passing**, 68% coverage (gate: 65%) — up from 41/41 at 63% before this phase's relocated embedder test |
| vector-store `pytest tests/unit` | **30/30 passing**, 89% coverage (gate: 80%) — was 7/30 collectible before fixing the missing `pytest-asyncio` dependency |
| rag-engine `pytest tests/unit` | **30/30 passing**, 92% coverage (gate: 80%) |
| embedding-server `pytest tests/unit` | **1/1 passing** (not coverage-gated) — was 1/15 collectible before relocating the two misplaced files |
| Updated `.github/workflows/ci.yml` | Valid YAML, all 9 jobs present, `test-integration` steps and `security-scan` `needs:` confirmed via direct parse |
| Full dependency set (all 4 fixed/new service requirements.txt files) | Verified via real `pip install` in isolated venvs per service — zero conflicts, `pip check` clean on each |

## Remaining work in this phase

- **ingestion's coverage gate (65% → 80%)**: the gap is concentrated in
  `db/session.py` (45%), `observability.py` (29%),
  `workers/kafka_config.py` (35%), `workers/scheduled_tasks.py` (40%)
  — all integration-test territory (need a live Postgres/Kafka to
  exercise meaningfully), not more mocked unit tests. Once
  `test-integration`'s newly-fixed ingestion step is contributing
  coverage data too, re-measure combined unit+integration coverage
  before raising the gate further.
- **Stage 11.2 (Locust)**: `tests/load/locustfile.py`, mocked
  `llm_provider="mock"` branch in `rag-engine/src/llm_router.py`,
  dispatch-rate CI assertion, documented 5,000 docs/sec extrapolation.
- **Stage 11.3 (Playwright RBAC)**: seed `readonly@tenant1.test` in
  `infra/keycloak/realm.json`, `dashboard/e2e/auth.setup.ts`, 5
  storageState-backed Playwright projects, new `workflow_dispatch`-only
  `e2e` CI job using `docker compose up -d`.
- **Stage 11.4 (adversarial security suite)**: `api-gateway/tests/security/`,
  OWASP API Top 10-scoped (BOLA, tenant-ID tampering, JWT tampering,
  function-level authz, rate-limit boundary).
- **Stage 11.5 (PHI leak scanner)**: Presidio + custom `PVH_MRN`
  recognizer (pattern confirmed against `seed_data.py`'s actual
  generator), scanning captured log/trace/error-body output from the
  Locust and Playwright runs once those exist.
- **`Makefile` / `.pre-commit-config.yaml` reconstruction**: both are
  still unrecoverable `[Binary file]` markers in the working dump.
  Stage 11.2 onward will likely want new `make` targets
  (`make load-test`, `make test-e2e`) — reconstructing these two files
  (or getting a fresh export) is a prerequisite for that, not solved
  in this session.

## For Phase 12 (Production Deployment)

Nothing new to add beyond what ADR-017 already flagged — Phase 11
doesn't change the Kubernetes NetworkPolicy, Aiven-managed-services, or
Vault production-auth items still sitting in that ADR's own risk
register. Once Stage 11.2 lands, its 5,000 docs/sec capacity math
(measured per-worker throughput × target worker count) is what Phase
12's cluster-sizing decision should actually be based on, rather than
the roadmap number alone.
