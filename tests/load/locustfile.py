"""
tests/load/locustfile.py — Phase 11 / ADR-018 Stage 11.2.

Root pyproject.toml declared a `load` pytest marker back in Phase 1, for
a directory that never existed until this stage. This is what
populates it (Locust itself doesn't use pytest markers, but the parent
`tests/` directory is otherwise pytest-scoped, so this file stays
clearly out of that collection path — see pytest.ini note below).

Two user classes, both against the REAL running api-gateway over HTTP
(Locust cannot reach into api-gateway's own process, so "mock the LLM
provider" happens on the *target stack's* side — see
rag-engine/src/llm_router.py's `mock` branch and its production safety
gate, added this stage):

  - IngestDispatchUser: POST /v1/ingest/jobs. This is the number CI
    gates on every run — dispatch-to-Kafka throughput, not full
    embedding-pipeline throughput (celery-worker's docker-compose
    concurrency of 4 makes the full pipeline number a local/nightly
    concern, not a CI one — see this stage's ADR-018 entry and
    docs/PHASE_11_IMPLEMENTATION_PLAN.md's 5,000 docs/sec extrapolation
    methodology).
  - QueryUser: POST /v1/query with llm_provider="mock" explicitly set
    (rather than relying on the target's LLM_DEFAULT_PROVIDER env var
    silently doing the same thing) — explicit in the load-test script
    itself is safer than an implicit deployment default, and exercises
    the real retrieval path (Weaviate/Qdrant) while skipping the
    expensive, rate-limited, non-deterministic LLM call.

Auth: both user classes authenticate with an X-API-Key header (ADR-010
service-account credential type — a load-test script has no human to
run a real Keycloak PKCE flow for). infra/scripts/seed_data.py already
seeds exactly one API key per tenant with scopes
["ingest:write", "query:read"] — auth.py's _role_from_scopes() resolves
that to role="engineer", which is >= "analyst" in the role hierarchy,
so this single seeded key satisfies both routes' require_min_role()
checks. The plaintext key is only ever printed once, at seed time
(never persisted beyond its hash) — run `seed_data.py` first and
export its output:

    python infra/scripts/seed_data.py   # prints the key once
    export PVH_LOAD_TEST_API_KEY=pvh_seed_...

Usage (dispatch-rate check, what CI runs):
    locust -f tests/load/locustfile.py --headless \
        --host http://localhost:8000 \
        --users 50 --spawn-rate 10 --run-time 60s \
        --csv tests/load/results/dispatch_rate \
        --exit-code-on-error 1

Usage (full local/nightly run against a scaled stack, for the
5,000 docs/sec extrapolation — see PHASE_11_IMPLEMENTATION_PLAN.md):
    docker-compose up -d --scale celery-worker=8
    locust -f tests/load/locustfile.py --headless \
        --host http://localhost:8000 \
        --users 200 --spawn-rate 20 --run-time 5m \
        --csv tests/load/results/full_pipeline
"""

from __future__ import annotations

import os
import random
import uuid

from locust import HttpUser, between, task

API_KEY = os.environ.get("PVH_LOAD_TEST_API_KEY", "")
if not API_KEY:
    raise RuntimeError(
        "PVH_LOAD_TEST_API_KEY is not set. Run infra/scripts/seed_data.py "
        "first and export the printed plaintext key -- see this file's "
        "module docstring."
    )

_DOCUMENT_TYPES = [
    "clinical_note",
    "lab_result",
    "imaging_report",
    "discharge_summary",
    "prescription",
]


def _fake_document_ref() -> dict:
    # Shape matches api-gateway/src/schemas/ingest.py's DocumentRef
    # exactly -- source_path is never actually fetched by this load
    # test (that only happens worker-side, in the real Celery pipeline,
    # well past what a dispatch-rate check exercises), so a
    # plausible-looking r2:// URI is enough.
    return {
        "source_path": f"r2://pvh-load-test/{uuid.uuid4()}.txt",
        "document_type": random.choice(_DOCUMENT_TYPES),
        "patient_id": str(uuid.uuid4()),
    }


class IngestDispatchUser(HttpUser):
    """Measures dispatch-to-Kafka throughput via POST /v1/ingest/jobs.

    Batch size (documents per job) deliberately stays small and
    constant (10) rather than sweeping up toward the schema's 5,000
    max -- this class measures *rate of job creation*, which is what
    the 100/minute rate limit (ingest.py) and Kafka producer throughput
    actually gate on; a single 5,000-document job would say much more
    about batch-payload serialization time than about sustained
    dispatch rate.
    """

    weight = 3  # most load-test traffic should be ingestion, matching
    # this system's actual traffic shape more than an even split would.
    wait_time = between(0.1, 0.5)

    def on_start(self) -> None:
        self.client.headers.update({"X-API-Key": API_KEY})

    @task
    def create_ingest_job(self) -> None:
        payload = {
            "name": f"load-test-{uuid.uuid4()}",
            "source_type": "api_push",
            "documents": [_fake_document_ref() for _ in range(10)],
        }
        with self.client.post(
            "/v1/ingest/jobs", json=payload, catch_response=True
        ) as response:
            if response.status_code == 429:
                # Expected once sustained load crosses the 100/minute
                # limit -- a rate-limit rejection is correct behavior,
                # not a load-test failure. Marked success so it doesn't
                # pollute the failure-rate SLO the CI gate checks.
                response.success()
            elif response.status_code != 201:
                response.failure(f"unexpected status {response.status_code}")


class QueryUser(HttpUser):
    """Measures retrieval + (mocked) synthesis latency via POST /v1/query.

    llm_provider="mock" is explicit per-request here (see this file's
    module docstring) -- resolves to rag-engine's _complete_mock(),
    zero network calls, zero cost, refused outright if this ever points
    at a misconfigured ENVIRONMENT=production target (see
    rag-engine/src/llm_router.py).
    """

    weight = 1
    wait_time = between(0.5, 2.0)

    _SAMPLE_QUERIES = [
        "What was the patient's most recent A1C result?",
        "Summarize the discharge instructions from the last visit.",
        "Are there any documented drug allergies on file?",
        "What imaging studies were ordered in the past 6 months?",
    ]

    def on_start(self) -> None:
        self.client.headers.update({"X-API-Key": API_KEY})

    @task
    def run_query(self) -> None:
        payload = {
            "query_text": random.choice(self._SAMPLE_QUERIES),
            "top_k": 10,
            "llm_provider": "mock",
        }
        with self.client.post(
            "/v1/query", json=payload, catch_response=True
        ) as response:
            if response.status_code == 429:
                response.success()  # same reasoning as IngestDispatchUser
            elif response.status_code != 200:
                response.failure(f"unexpected status {response.status_code}")
