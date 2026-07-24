# Phase 4 — Core Ingestion Pipeline: Implementation Plan

**Status:** Proposed
**Author:** Architecture review, 2026-07-23
**Depends on:** Phase 2 (Database Foundation) ✅, Phase 3 (Auth & RBAC) ✅
**Supersedes-in-part:** docs 04/06/13/19-24's ingestion design, per ADR-009
**Related:** ADR-009 (Aiven/OpenAI/native-multitenancy pivot), ADR-010 (API-key RLS bootstrap)

---

## 0. Where the repo actually stands today

Before scoping new work, here's what Phase 1-3 already shipped, and — importantly — what
Phase 4's target directories currently contain (mostly empty stubs):

| Area | State |
|---|---|
| `api-gateway/` | Full DB models (8 tables), Alembic 001-004, RLS + FORCE RLS, tenant-scoped async sessions, dual JWT/API-key auth middleware, RBAC guards, `admin.py` router | ✅ Done |
| `ingestion/src/parsers/` | Empty `__init__.py` only | ❌ Phase 4 |
| `ingestion/src/chunkers/` | Empty `__init__.py` only | ❌ Phase 4 |
| `ingestion/src/embeddings/` | Empty `__init__.py` only | ❌ Phase 4 |
| `ingestion/src/workers/` | Empty `__init__.py` only | ❌ Phase 4 |
| `ingestion/src/db/__init__.py` | Stub: hardcoded tenant IDs, a bare `get_sync_session()` with no tenant scoping | ⚠️ Needs Phase-2-grade RLS treatment |
| `ingestion/embedding-server/` | Real FastAPI service, but returns zero-vector stubs unless a real clinical-bert checkpoint loads — **not wired into any ingestion path** | Stays parked (ADR-009) |
| `vector-store/src/interface.py` | ABC + `get_store()` that **raises `NotImplementedError`** for both backends | ❌ No concrete implementation exists yet |
| `scripts/create_kafka_topics.py` | Real, cloud-aware (SASL/SSL for Aiven), creates `doc-ingest`/`doc-chunk`/`doc-embed`/`doc-dlq` | ✅ Done, reusable as-is |
| `scripts/setup_weaviate_schema.py` | Real — single `PatientDocument` collection, **native multi-tenancy**, `auto_tenant_creation=True` | ✅ Done, defines the pattern Phase 4 must follow |
| `scripts/setup_qdrant_schema.py` | Real — per-tenant Qdrant collections (DR path) | ✅ Done, out of scope for Phase 4 |
| `api-gateway/src/routers/ingest.py` | **Does not exist** | ❌ Phase 4 |
| `api-gateway/src/kafka_utils.py` | **Does not exist** | ❌ Phase 4 |
| `api-gateway/src/db/crud.py` | Has `create_ingestion_job`, `get_ingestion_job`, `list_ingestion_jobs`, `create_document` — **missing** `update_job_progress`, `mark_document_failed`, any embedding-status transition helper | ⚠️ Needs extension |

So Phase 4 isn't starting from the doc 19-24 reference code as-is — it's starting from stub
directories, a schema that's ready, and one live architectural pivot (ADR-009) that changes
three of the five original Phase 4 dependencies. That reconciliation comes first.

---

## 1. Reconcile design docs with ADR-009 before writing any code

| Original design (docs 04/06/13/19-24) | ADR-009 replaces it with | Effect on Phase 4 |
|---|---|---|
| Self-hosted `clinical-bert` pod, 768-dim, Phase 5 dependency | **OpenAI `text-embedding-3-large`**, `EMBEDDING_DIMENSIONS=1536` (Matryoshka-shortened) | Phase 4 has **no dependency on a live embedding pod**. `ingestion/embedding-server/` stays parked. This actually *removes* a Phase 1 risk-register item ("clinical-bert pod slow to start, blocks workers on boot") rather than requiring its mitigation. |
| AWS S3 (`boto3.client('s3')` against `s3.amazonaws.com`) | **Cloudflare R2** (S3-compatible, `endpoint_url=R2_ENDPOINT_URL`) | Parsers need an R2-aware client wrapper, not bare `boto3.client('s3')` with AWS defaults. |
| Per-tenant Weaviate collection `PatientDocument_{tenant_id}` | **Single `PatientDocument` collection, native multi-tenancy**, `collection.with_tenant(tenant_id)` | `weaviate_store.py` (doesn't exist yet) must follow the new pattern from day one — there is no legacy code to migrate, so this is simply "build it right the first time." |
| AWS MSK | Aiven Kafka / local KRaft, SASL_SSL via `.env` | `scripts/create_kafka_topics.py` already handles this. The ingestion producer/consumer must read the **same** `KAFKA_SECURITY_PROTOCOL`/`KAFKA_USERNAME`/`KAFKA_PASSWORD`/`KAFKA_SASL_MECHANISM`/`KAFKA_SSL_*` vars — today `ingestion/src/config.py` doesn't expose them as typed settings, only the topic-creation script reads them ad hoc via `os.getenv`. |
| — | ADR-009's explicit compliance caveat | OpenAI embeddings are accepted **only** for the synthetic-data Phase 1-6 window. Phase 4 code should not quietly normalize this — see §9 for the concrete guardrail. |

**One inconsistency worth naming directly:** ADR-009 pivoted embeddings and storage, but did
**not** revisit the vector-store `Chunk`/`SearchResult` dataclasses in
`vector-store/src/interface.py`, which are backend-agnostic and need no change. Good — that
interface is still the right contract for whatever `WeaviateStore` Phase 4 adds.

---

## 2. The one scope call that most changes this plan's size

Doc 06's Phase 4 "Done" criteria says: *"10,000 synthetic docs ingested end-to-end **·
Embeddings stored in Weaviate** · Job status accurate in real-time · Failed docs land in DLQ
without crashing workers."*

But `vector-store/src/interface.py::get_store()` raises `NotImplementedError` today, and a
full Weaviate implementation (hybrid search, health checks, namespace polish, Qdrant DR
failover) is explicitly Phase 6 in the original phase breakdown.

**Recommendation: build a *minimal* `WeaviateStore` now — `upsert()` and `health_check()`
only, using native multi-tenancy — as part of Phase 4.** Leave `search()` raising
`NotImplementedError` until Phase 6/7 (RAG query needs it, ingestion doesn't). This is a
deliberate, narrow pull-forward of a small slice of Phase 6, not scope creep, and it's the
only way Phase 4 can actually satisfy its own doc 06 done-criteria. §11 has a draft ADR
recording this so it doesn't read as silent scope drift later.

*(Alternative, if you'd rather keep Phase 4 strictly to ingestion mechanics: stub the sink
with a `NullVectorStore` that logs+no-ops, and treat "embeddings stored" as a Phase 6
carry-over. This is a smaller Phase 4 but means you can't actually prove the pipeline works
end-to-end until Phase 6 lands. I'd only take this path if Phase 6 is imminent.)*

---

## 3. New / modified files

### 3.1 `ingestion/src/parsers/`
```
r2_client.py          # boto3 client factory bound to R2_ENDPOINT_URL / R2_ACCESS_KEY_ID / R2_SECRET_ACCESS_KEY
pdf_parser.py          # PyMuPDF — `import pymupdf` (NOT `import fitz`; fitz is now a legacy
                        # alias only — see footnote [1]). Page-by-page extraction, "[Page N]" markers.
hl7_parser.py           # `python-hl7` (`import hl7`) — see footnote [2] for why this beats hl7apy.
                        # PID/OBX/DG1 segment extraction into flat text, matching doc 21's shape.
plain_text_parser.py    # utf-8 decode, latin-1 fallback for legacy clinical docs (unchanged from doc 37)
__init__.py             # get_parser_for_uri(path) factory, dispatches on file extension
```

Key correction vs. the reference docs: `source_path` in the `documents` table (migration 004)
is a free-text column already shaped like `s3://bucket/raw/{tenant}/{doc}/original.ext` in the
original design — for R2 this should be `r2://{bucket}/raw/{tenant_id}/{patient_id}/{doc_id}/original.{ext}`,
matching what `seed_data.py`'s sample documents already write (`r2://pvh-documents-dev/seed/...`).
The parser factory should strip the `r2://` prefix the same way the reference `s3://` parsers
strip theirs.

### 3.2 `ingestion/src/chunkers/splitter.py`
```python
from langchain_text_splitters import RecursiveCharacterTextSplitter  # NOT langchain.text_splitter
```
This import path changed upstream since the original docs were written — `RecursiveCharacterTextSplitter`
now lives in the standalone `langchain-text-splitters` package (see footnote [3]). Everything
else about doc 25's `chunk_text()` design (clinical separator priority list, `Chunk` dataclass
with `text`/`index`/`metadata`, empty-chunk filtering) is still sound and should be reused as-is.

### 3.3 `ingestion/src/embeddings/openai_embedder.py` (replaces the doc 25 `clinical_bert.py` design)
```python
async def embed_batch(texts: list[str]) -> list[list[float]]:
    """POST to OpenAI embeddings, dimensions=settings.EMBEDDING_DIMENSIONS (1536).
    tenacity retry on RateLimitError / APIConnectionError / APITimeoutError,
    exponential backoff. Batches capped at a safe request size (OpenAI's own
    guidance: keep well under the 8,191-token-per-input ceiling per chunk —
    chunk_size=512 chars leaves comfortable headroom, see footnote [4])."""
```
Model confirmed still current and *not* deprecated as of mid-2026 — no successor to the
`text-embedding-3` series has shipped; the only deprecated OpenAI embedding model is the older
`text-embedding-ada-002` (footnote [4]). `EMBEDDING_DIMENSIONS=1536` already matches what
`vector-store/src/config.py` and `scripts/setup_qdrant_schema.py` expect — no config drift to
fix here, just the actual embedding call that's currently missing.

Add a lightweight token/cost log line per batch (`tiktoken`-counted or `usage.total_tokens`
from the response) — cheap now, saves a surprise later; full cost dashboards are Phase 10.

### 3.4 `ingestion/src/db/` (extend the existing stub, don't replace it)
The existing `get_all_tenant_ids()` is hardcoded and `get_sync_session()` has **no tenant
scoping at all** — that's fine for Phase 1 (no RLS existed yet) but is now a real gap since
migration 003/004 put every table Phase 4 touches under `FORCE ROW LEVEL SECURITY`. Mirror the
pattern `api-gateway/src/db/session.py::get_tenant_session()` and `seed_data.py::_set_tenant_context()`
already established — `set_config('app.tenant_id', tid, true)`, not a literal `SET LOCAL`
string (can't bind params into `SET`/`SET LOCAL` over the wire protocol).

```python
def get_all_tenant_ids() -> list[str]:
    # replace the hardcoded pair with: SELECT id FROM tenants

@contextmanager
def get_tenant_sync_session(tenant_id: str) -> Session:
    # sync equivalent of api-gateway's get_tenant_session() — psycopg2, not asyncpg

def update_job_progress(tenant_id: str, job_id: str, increment: int = 1) -> None:
    # atomic doc_count_processed += n; status -> completed when processed+failed >= total

def mark_document_failed(tenant_id: str, document_id: str, job_id: str, error: str) -> None:
    # documents.embedding_status = 'failed'; ingestion_jobs.doc_count_failed += 1

def update_document_embedding_status(
    tenant_id: str, document_id: str, status: str,
    chunk_count: int | None = None, model_version: str | None = None,
) -> None:
    # pending -> processing -> completed | failed
```
`update_job_progress` / `mark_document_failed` **do not exist anywhere in the current
codebase** (they were sketched in the reference docs' `crud.py` but that file's async
API-gateway sibling stopped short of them too) — this is genuinely new code, not a port.

### 3.5 `ingestion/src/workers/`
```
batch_worker.py     # Celery app + process_document task — see §5 for the full task shape
                     # and §6 for the DLQ-on-exhaustion fix
stream_consumer.py  # AIOKafkaConsumer('doc-ingest', group_id='pvh-ingestion-workers'),
                     # manual commit only after successful Celery dispatch (doc 21's pattern
                     # is correct here) — must read the same KAFKA_SECURITY_PROTOCOL/SASL/SSL
                     # settings as create_kafka_topics.py, added to config.py per §1
dlq_producer.py      # small AIOKafkaProducer wrapper: publish_to_dlq(payload, error)
```

### 3.6 `vector-store/src/weaviate_store.py` (new)
```python
class WeaviateStore(VectorStoreInterface):
    def __init__(self, tenant_id: str):
        self._collection = self._client.collections.get("PatientDocument")
        self._tenant = self._collection.with_tenant(tenant_id)   # native multi-tenancy (ADR-009)

    async def upsert(self, doc_id, chunks, vectors) -> None: ...   # Phase 4
    async def health_check(self) -> bool: ...                     # Phase 4
    async def search(self, query, top_k, filters) -> list:
        raise NotImplementedError("Hybrid search lands in Phase 6/7")
    async def delete(self, doc_id) -> None:
        raise NotImplementedError("Phase 6")
```
Wire `vector-store/src/interface.py::get_store()` to actually return this instead of raising —
today it's 100% stub. `QdrantStore` stays `NotImplementedError` (DR path, explicitly Phase 6+).

### 3.7 `api-gateway/src/routers/ingest.py` (new — doesn't exist)
```
POST /v1/ingest/jobs   require_min_role("engineer")  -> crud.create_ingestion_job
                                                       + kafka_utils.publish_ingest_job
                                                       + crud.write_audit_log(action="document_ingest")
GET  /v1/ingest/jobs/{id}   require_min_role("engineer")
GET  /v1/ingest/jobs        require_min_role("engineer")
```
Needs:
- `api-gateway/src/schemas/ingest.py` (new) — `IngestJobCreate` / `IngestJobResponse` Pydantic models (doc 32's shapes are still fine, adjust `embedding_model` default to `"text-embedding-3-large"`)
- `api-gateway/src/kafka_utils.py` (new) — `publish_ingest_job()`
- `main.py` lifespan: confirm `app.state.kafka` (an `AIOKafkaProducer`) is actually started — Phase 1-3 focus was DB/auth, this may not be wired yet; verify before assuming it exists
- Mount: `app.include_router(ingest.router, prefix="/v1/ingest", tags=["Ingestion"])`

### 3.8 `ingestion/src/config.py` additions
```
KAFKA_SECURITY_PROTOCOL, KAFKA_USERNAME, KAFKA_PASSWORD, KAFKA_SASL_MECHANISM,
KAFKA_SSL_CAFILE, KAFKA_SSL_CERTFILE, KAFKA_SSL_KEYFILE   # promote from ad-hoc os.getenv (today
                                                            # only create_kafka_topics.py reads these)
OPENAI_API_KEY
EMBEDDING_BATCH_SIZE   # default e.g. 100 texts/request, tune against OpenAI rate limits
```

### 3.9 Dependency additions (verified current as of July 2026)
`ingestion/requirements.txt`:
```
boto3                          # R2 is S3-compatible; no extra client library needed
pymupdf                        # import pymupdf, not fitz — see footnote [1]
hl7                            # pip name is "hl7" even though the import is `import hl7` — python-hl7 project
langchain-text-splitters       # NOT langchain — see footnote [3]
celery[redis]
aiokafka
openai
tenacity
sqlalchemy
psycopg2-binary
pydantic-settings
python-dotenv
```
`api-gateway/requirements.txt`: uncomment the already-present-but-commented `aiokafka` and `tenacity` lines — no new entries needed.
`vector-store/requirements.txt`: no change (already has `weaviate-client`, `qdrant-client`).

---

## 4. Build sequence (and why this order)

1. **Parsers + R2 client** — no DB/Kafka dependency, unit-testable standalone against fixture bytes
2. **Chunker** — pure function, unit-testable standalone
3. **Embedder** — needs `OPENAI_API_KEY`, unit-testable with a mocked `AsyncOpenAI` client
4. **`ingestion/src/db/` CRUD extensions** — needs Postgres (docker-compose already provides it)
5. **`WeaviateStore` minimal impl** — needs the `weaviate` container
6. **`batch_worker.py`** — wires 1-5 into one Celery task
7. **`dlq_producer.py` + retry-exhaustion wiring** — see §6, this is the part the reference docs left incomplete
8. **`stream_consumer.py`** — Kafka → Celery dispatch, depends on 6 existing
9. **`api-gateway/ingest.py` router + `kafka_utils.py`** — the "front door," deliberately last since it needs something to trigger
10. **Tests** — unit tests alongside each module as it's built; one true end-to-end integration test once the chain is complete

---

## 5. Job lifecycle / state machine

```
ingestion_jobs.status:  queued -> running (on first doc processed) -> completed | failed | cancelled
documents.embedding_status:  pending -> processing -> completed | failed
```

The atomic-increment SQL pattern sketched in the reference docs (`doc_count_processed +
doc_count_failed >= doc_count_total` → auto-complete) is sound and should be kept — but it
means a job that's 40% failed still reports `status: "completed"`. That's a legitimate UX
question worth deciding explicitly rather than inheriting by accident:

**Recommendation:** don't add a new DB status value (avoids another migration + CHECK
constraint edit). Instead compute a display-only label at the API layer —
`"completed_with_errors"` when `doc_count_failed > 0` and `status == "completed"` — in the
`IngestJobResponse` serializer. Keeps the DB enum small and stable, keeps the UX honest.

---

## 6. DLQ design — closing a real gap in the reference docs

Worth stating plainly: **nothing in the original design (docs 21/24) actually produces to the
`doc-dlq` Kafka topic.**

- Doc 21's `stream_consumer.py`: dispatch failure → no Kafka commit → the message is simply
  redelivered by the consumer group. That's retry, not DLQ.
- Doc 21's `batch_worker.py`: exception → `self.retry()` → after `max_retries`, Celery marks
  the task `FAILED` internally. Nothing publishes anywhere else.
- Doc 24's runbooks (`Kafka Consumer Lag`, etc.) assume a `doc-dlq` topic is populated and
  inspectable — but the topic-creation script is the only place `doc-dlq` is even referenced
  before this plan.

**Phase 4 needs to close this explicitly:**

```python
@celery_app.task(bind=True, max_retries=3, default_retry_delay=60,
                 queue="doc-ingest", name="pvh.process_document")
def process_document(self, doc_id, r2_uri, tenant_id, job_id, chunk_size=512, chunk_overlap=50):
    try:
        raw_text = get_parser_for_uri(r2_uri).extract(r2_uri)
        chunks   = chunk_text(raw_text, chunk_size, chunk_overlap)
        vectors  = asyncio.run(embed_batch([c.text for c in chunks]))
        asyncio.run(get_store(tenant_id).upsert(doc_id, chunks, vectors))
        update_document_embedding_status(tenant_id, doc_id, "completed",
                                          chunk_count=len(chunks),
                                          model_version=settings.EMBEDDING_MODEL_VERSION)
        update_job_progress(tenant_id, job_id, increment=1)
    except Exception as exc:
        if self.request.retries >= self.max_retries:
            # terminal failure — route to Kafka DLQ, then close out cleanly.
            # Do NOT call self.retry() again here; let the task end normally so
            # Celery's own retry bookkeeping doesn't fight the DLQ routing.
            publish_to_dlq({"doc_id": doc_id, "job_id": job_id, "tenant_id": tenant_id,
                            "r2_uri": r2_uri}, error=str(exc))
            mark_document_failed(tenant_id, doc_id, job_id, str(exc))
            return
        raise self.retry(exc=exc)
```

This is the piece that makes doc 06's "Failed docs land in DLQ without crashing workers"
criterion actually true, rather than aspirational.

---

## 7. Testing plan

**Unit** (`tests/unit/`, no Docker required):
- `test_parsers.py` — mock the R2 client, assert PDF/HL7/plain-text extraction shapes
- `test_chunker.py` — overlap correctness, empty-chunk filtering, separator priority
- `test_embedder.py` — mock `AsyncOpenAI`, assert retry fires on `RateLimitError`, assert `dimensions=1536` is actually passed
- `test_dlq_routing.py` — mock the producer, assert DLQ payload shape on simulated retry exhaustion

**Integration** (`tests/integration/`, requires docker-compose: postgres + redis + kafka + weaviate):
- `test_ingestion_end_to_end.py` — seed one tenant, push a small fixture PDF to R2 (or a local
  S3-compatible stand-in in CI, see open decision #4 below), run `process_document` with
  `CELERY_TASK_ALWAYS_EAGER=True`, assert `ingestion_jobs.doc_count_processed` increments,
  `documents.embedding_status == 'completed'`, and a vector actually landed in the tenant's
  Weaviate shard
- `test_dlq_end_to_end.py` — force a parser failure (corrupt fixture), assert a message lands
  on `doc-dlq`, `embedding_status == 'failed'`, `doc_count_failed` increments, and the worker
  keeps consuming the next message without crashing
- Extend the existing `test_rls_isolation_core_tables.py` pattern: a job created for tenant A
  must be invisible/non-incrementable from a tenant B session — natural continuation of the
  Phase 2 RLS suite, and the cheapest possible regression test for the new `ingestion/src/db/`
  tenant-scoping code in §3.4

**CI change required, not just app code:** `.github/workflows/ci.yml`'s `test-integration` job
currently only spins up `postgres` + `redis` services. Add `kafka` and `weaviate` service
containers (or switch that job to `docker compose up -d` against the repo's own
`docker-compose.yml`) before any Phase 4 integration test can run in CI.

---

## 8. Definition of Done

- [ ] `make dev` / `dev-lite` still boots cleanly with the new dependencies
- [ ] `POST /v1/ingest/jobs` (engineer+) queues a job row and publishes to `doc-ingest`
- [ ] Celery worker consumes `doc-ingest` (stream path) **and** can process a directly-dispatched batch job (doc 06 asks for both `s3_batch`/`kafka_stream` support)
- [ ] All three parsers (PDF / HL7 / plain text) produce chunkable text from R2-stored fixtures
- [ ] Chunks embedded via OpenAI, confirmed 1536-dim vectors returned
- [ ] Vectors upserted into the shared `PatientDocument` Weaviate collection, correctly tenant-scoped via `.with_tenant()`
- [ ] `ingestion_jobs.doc_count_processed` / `doc_count_failed` update atomically and in real time
- [ ] `documents.embedding_status` transitions `pending → processing → completed|failed`
- [ ] A forced parser/embedding failure lands a message on `doc-dlq` and does **not** crash the worker
- [ ] RLS still enforced on every new write path — proven by an integration test, not just code review
- [ ] Unit + integration suites pass in CI (kafka + weaviate added to `ci.yml`)
- [ ] A 10k-synthetic-doc run completed at least once locally (a crude asyncio/Locust script is enough — the full Locust harness with SLA gates is Phase 11's job, Phase 4 just needs to prove the pipeline doesn't fall over at that volume)

---

## 9. ADR-009 compliance guardrail (small but don't skip it)

ADR-009 was explicit that OpenAI embeddings are acceptable **only** while ingestion handles
synthetic data. Phase 4 should encode that as more than a comment. Concretely: add a startup
assertion in `ingestion/src/config.py` — e.g. refuse to boot if
`EMBEDDING_PROVIDER == "openai"` **and** an (currently nonexistent, so: to be added) `ALLOW_REAL_PHI`
flag is `true` without a signed-BAA acknowledgment flag also being set. This costs almost
nothing to add now and turns "must not carry into a real-PHI environment" from a documentation
promise into something the code actually enforces before anyone forgets.

---

## 10. Risk carryover + one new risk

| Risk | Status |
|---|---|
| clinical-bert pod slow to start, blocks workers on boot | **Resolved as a side effect of ADR-009** — Phase 4 doesn't depend on that pod at all now. Worth noting explicitly since it was Critical severity in the original register. |
| Weaviate HNSW build time at scale | Still relevant — this is the *first* real write path into the native-multi-tenant `PatientDocument` collection. Test against the already-seeded 1,000-patient set before any 10k+ doc load test. |
| Docker Compose RAM exhaustion | Slightly *improved* vs. original design — `embedding-server` isn't in the hot path anymore (OpenAI is), so local RAM pressure from Phase 4 work is lower than the original architecture assumed. |
| **New: OpenAI rate limits / cost at 10k-doc test scale** | Not in the original register (it assumed self-hosted embeddings, which have no per-token cost or provider rate limit). Cap batch size and concurrency in `openai_embedder.py` from the start — don't bolt this on after the first 429. |

---

## 11. Draft ADR-011 (for your sign-off — record if accepted)

> **ADR-011: Phase 4 pulls a minimal Weaviate write path forward from Phase 6; DLQ routing is
> explicit Kafka-topic-based, not Celery-retry-exhaustion-only**
>
> **Decision:** `vector-store/src/weaviate_store.py` ships in Phase 4 with `upsert()` +
> `health_check()` only (native multi-tenancy per ADR-009); `search()` stays deferred to
> Phase 6/7. Terminal document-processing failures explicitly publish to the `doc-dlq` Kafka
> topic before the Celery task ends, rather than relying on Celery's internal retry-exhaustion
> state (which the doc 24 runbooks incorrectly assumed was already wired to Kafka).
>
> **Why:** Phase 4's own done-criteria (doc 06) requires "embeddings stored in Weaviate" and
> "failed docs land in DLQ" — neither was actually implementable from the reference docs as
> written. This ADR records that the fix was a deliberate, scoped decision, not silent scope
> creep into Phase 6.
>
> **Trade-off:** a small amount of Phase 6 work (one backend, two methods) ships two phases
> early. Full hybrid search, Qdrant DR wiring, and namespace-manager polish are unaffected and
> remain Phase 6.

---

## 12. Open decisions — need your call before/while building

1. **Minimal Weaviate write in Phase 4** (recommended, §2/§11) vs. deferring all vector storage to Phase 6 with a no-op sink.
2. **R2 fixtures in CI** — mock `boto3` entirely for CI (recommended: no live R2 credentials needed in CI secrets) vs. adding a local S3-compatible container (e.g. MinIO) to `docker-compose.yml` for integration tests.
3. **"completed_with_errors"** — API-layer-only label (recommended, §5, no migration) vs. a new DB status value.
4. Confirm `hl7` (python-hl7) is acceptable given it's a smaller/simpler library than `hl7apy` — it covers PID/OBX/DG1 segment access fine for the doc 21 use case, but doesn't do full HL7 spec validation the way `hl7apy` claims to (moot here since `hl7apy` is the one that's actually gone stale — see footnote [2]).
5. Celery beat / scheduled cleanup tasks (doc 34's `scheduled_tasks.py`) — recommend keeping in Phase 10 as originally scoped; Phase 4 stays focused on the ingest path only.

---

## 13. Implementation status (added post-build)

All decisions in §12 were made and Phase 4 was fully implemented — see
`MANUAL_INTEGRATION_NOTES.md` in the delivery for the handful of items (mainly `main.py`,
which came through unreadable in the original repo paste) that need manual merging. Every
generated Python file was syntax-checked, and everything mockable was actually installed and
run with `pytest` — 29 unit tests, all passing. That process caught three real bugs a
plausible-looking-but-untested draft would have shipped with: an empty-string `boto3`
`endpoint_url` raising at client construction, `AsyncOpenAI(api_key="")` raising at *import*
time rather than at first real call, and `AIOKafkaProducer`/`AIOKafkaConsumer` needing an
`ssl.SSLContext` object (not a bare `ssl_cafile` string) — the last one would only have
surfaced the first time this ran against a real SASL_SSL broker like Aiven. Full details in
`MANUAL_INTEGRATION_NOTES.md`'s validation section.

---

## Footnotes (verified July 2026, since several reference docs predate a couple of upstream changes)

1. **PyMuPDF import:** `import pymupdf` is now the recommended, future-proof import; `import fitz`
   is kept only as a legacy alias (works identically, but new code should prefer `pymupdf`).
   Source: PyMuPDF's own PyPI page and docs.
2. **HL7 library choice:** `hl7apy`'s last PyPI release (1.3.5) has had no update in over a
   year and independent maintenance trackers flag it as inactive. `python-hl7` (PyPI name
   `hl7`) is actively maintained on GitHub and explicitly supports Python 3.9-3.13 — matching
   this repo's Python 3.11 target. The original doc 21 already used `import hl7`
   (python-hl7's import name), so no code pattern changes here, just a confirmation the
   original choice holds up.
3. **LangChain text splitters:** `RecursiveCharacterTextSplitter` now ships in the standalone
   `langchain-text-splitters` package (`from langchain_text_splitters import
   RecursiveCharacterTextSplitter`), not the monolithic `langchain` package's
   `langchain.text_splitter` module the reference docs (07-12, 19-24) were written against.
4. **OpenAI embeddings:** `text-embedding-3-large` remains OpenAI's current, non-deprecated
   large embedding model as of mid-2026, with no announced successor; the only deprecated
   embedding model in the lineage is the older `text-embedding-ada-002`. The `dimensions`
   parameter (Matryoshka shortening) this repo already relies on for `EMBEDDING_DIMENSIONS=1536`
   is the documented, OpenAI-recommended way to shrink vector size without re-training.
