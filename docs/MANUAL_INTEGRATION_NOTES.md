# Phase 4 — Manual Integration Notes

## What was actually validated (not just generated)

Before finalizing, every Python file was syntax-checked, and the fully-mockable pieces were
installed and run for real with `pytest` (29 unit tests, all passing): parsers (PDF via a
real PyMuPDF-generated fixture, HL7 via a real python-hl7 parse, plain text, R2 URI parsing),
the chunker, the OpenAI embedder (batching, retry-on-429, dimensions param), the DLQ producer,
and `process_document()`'s retry-exhaustion branch (using Celery's `Task.apply(...,
retries=N)` to simulate "final attempt" directly). `WeaviateStore` was import-checked and its
deterministic chunk-UUID logic was verified. `docker-compose.yml` and `ci.yml` were both
YAML-validated.

That process caught three real bugs before delivery, not just typos:
1. `boto3.client(endpoint_url="")` raises `ValueError: Invalid endpoint` — fixed to pass `None`
   when `R2_ENDPOINT_URL` is unset (`r2_client.py`).
2. `AsyncOpenAI(api_key="")` raises `OpenAIError` **at construction**, which would have crashed
   on `import openai_embedder` alone in any environment without `OPENAI_API_KEY` set (CI
   included) — fixed by making the client lazy (`_get_client()`), constructed on first real use.
3. `AIOKafkaProducer`/`AIOKafkaConsumer` take `ssl_context` (an `ssl.SSLContext`), **not** a bare
   `ssl_cafile` string — the first draft would have raised `TypeError` the first time it ran
   against a real SASL_SSL broker (Aiven). Fixed via `aiokafka.helpers.create_ssl_context()` in
   a new shared `ingestion/src/workers/kafka_config.py`, and verified end-to-end against a real
   self-signed cert.

The integration tests (`tests/integration/`) could **not** be run here — they need live
Postgres/Kafka/Weaviate, which this sandbox doesn't have. They're syntax-valid and logically
reviewed, but treat them as "should work" rather than "proven," until you run them against
your actual `docker-compose` stack.

---

Everything else in this delivery is a complete, drop-in file. These specific items need a
human to merge them by hand, because the source files either weren't readable when this repo
was pasted into the planning conversation (`main.py`, `api-gateway/src/config.py` both came
through as `[Binary file]`), or because they're small additions to a file I do have in full
but don't want to silently overwrite in case your local copy has since diverged.

---

## 1. `api-gateway/src/main.py` — mount the ingest router + confirm Kafka producer

I don't have this file's current content, so I can't safely hand you a full replacement.
Two things to check/add:

**a) Router mount** — add alongside however the existing `admin` router is mounted:
```python
from .routers import ingest  # add this import

app.include_router(ingest.router, prefix="/v1/ingest", tags=["Ingestion"])
```

**b) Kafka producer in the lifespan** — `api-gateway/src/routers/ingest.py` reads
`request.app.state.kafka` and expects an already-started `AIOKafkaProducer`. If Phase 1-3's
`main.py` doesn't already start one (Phase 1-3 focus was DB/auth, not messaging — it's genuinely
possible this isn't there yet), add to the lifespan:
```python
from aiokafka import AIOKafkaProducer
from .config import settings

@asynccontextmanager
async def lifespan(app: FastAPI):
    ...  # existing db_pool / vault setup
    kafka_kwargs = {
        "bootstrap_servers": settings.KAFKA_BROKERS,
        "security_protocol": getattr(settings, "KAFKA_SECURITY_PROTOCOL", "PLAINTEXT"),
    }
    if getattr(settings, "KAFKA_USERNAME", "") and getattr(settings, "KAFKA_PASSWORD", ""):
        kafka_kwargs.update(
            sasl_mechanism=getattr(settings, "KAFKA_SASL_MECHANISM", "PLAIN"),
            sasl_plain_username=settings.KAFKA_USERNAME,
            sasl_plain_password=settings.KAFKA_PASSWORD,
        )
    # IMPORTANT: aiokafka takes `ssl_context` (an ssl.SSLContext), NOT a
    # bare `ssl_cafile` string — this bit me once already while building
    # ingestion's dlq_producer.py/stream_consumer.py (see
    # ingestion/src/workers/kafka_config.py's docstring). Use
    # aiokafka.helpers.create_ssl_context(), not a raw path kwarg.
    if getattr(settings, "KAFKA_SSL_CAFILE", ""):
        from aiokafka.helpers import create_ssl_context
        kafka_kwargs["ssl_context"] = create_ssl_context(cafile=settings.KAFKA_SSL_CAFILE)

    app.state.kafka = AIOKafkaProducer(**kafka_kwargs)
    await app.state.kafka.start()
    yield
    await app.state.kafka.stop()
    ...  # existing shutdown
```
If `api-gateway/src/config.py` doesn't already expose `KAFKA_SECURITY_PROTOCOL` etc., add the
same fields ingestion's `config.py` now has (see this repo's updated
`ingestion/src/config.py` for the exact field list) — `KAFKA_BROKERS` almost certainly already
exists (referenced by `scripts/create_kafka_topics.py`), the SASL/SSL fields may not.

---

## 2. `api-gateway/requirements.txt` — uncomment two already-present lines

No new dependency needed — the file already lists these, just commented out:
```diff
-# aiokafka>=0.12.0,<0.13.0
+aiokafka>=0.12.0,<0.13.0
```
```diff
-# tenacity>=9.0.0,<10.0.0
+tenacity>=9.0.0,<10.0.0
```
(`tenacity` isn't strictly required by the Phase 4 router itself, but harmless to enable now —
Phase 8's REST API hardening will want it too.)

No other `api-gateway/src/config.py` changes are needed for Phase 4 — `WEAVIATE_URL` /
`WEAVIATE_API_KEY` already exist there (confirmed via `tests/unit/test_config.py`), and
`api-gateway` never needs `OPENAI_API_KEY` — only the ingestion service calls OpenAI directly.

---

## 3. Cross-package import: `ingestion` needs `vector_store` importable

`ingestion/src/workers/batch_worker.py` does `from vector_store.interface import Chunk,
get_store`. This repo's README documents **separate venvs per service**
(`venv-api-gateway`, `venv-ingestion`, `venv-rag-engine`, `venv-vector-store`), so
`venv-ingestion` does **not** have `vector-store/src` on its import path by default — this is
a real gap independent of anything built here, not something Phase 4 introduced.

**Docker (docker-compose.yml, already handled by the files in this delivery):**
`ingestion/Dockerfile` now builds with the **repo root** as context (not `./ingestion`) so it
can `COPY vector-store/src/ ./vector_store/` into the image alongside `ingestion/src/`. The
three new services in `docker-compose.yml` (`celery-worker`, `celery-beat`, `kafka-consumer`)
already use `context: .` / `dockerfile: ingestion/Dockerfile` — no action needed there.

**Local (non-Docker) dev, per the README's venv workflow — pick one:**
```powershell
# Option A — editable install of vector-store into venv-ingestion
.\venv-ingestion\Scripts\activate
pip install -e ..\vector-store

# Option B — PYTHONPATH, no install
.\venv-ingestion\Scripts\activate
$env:PYTHONPATH = "..\vector-store\src;$env:PYTHONPATH"
```
Option A is cleaner long-term (survives new shells without re-exporting PYTHONPATH); Option B
is faster to try once. Either way, `vector-store/src/` currently has no `setup.py`/
`pyproject.toml` of its own — `pip install -e` needs one added (a few lines: `name`,
`version`, `packages=["."]` is enough) if you go with Option A. Not included in this delivery
since it's a small, separate packaging decision or you may already have a preferred approach.

---

## 4. `scripts/dev.ps1` / `scripts/dev.bat` — no code change required, banner text optional

Both scripts call `docker compose up -d` with no service names, so the three new services
(`celery-worker`, `celery-beat`, `kafka-consumer`) start automatically — Compose builds and
starts every defined service by default. The only thing worth updating, purely cosmetic, is
the printed "stack ready" banner in both scripts to mention the new services exist. Not
functionally required.

---

## 5. `.env` — nothing required, a few optional additions

Everything Phase 4 needs already has a sensible default in `ingestion/src/config.py`
(`EMBEDDING_BATCH_SIZE=100`, `ALLOW_REAL_PHI=false`) or already exists in `.env.example`
(`OPENAI_API_KEY`, `R2_*`, `KAFKA_BROKERS`, `EMBEDDING_MODEL_VERSION`,
`EMBEDDING_DIMENSIONS`). You do need a **real** `OPENAI_API_KEY` (not the placeholder) for
anything to actually embed — the unit tests never call the real API, but the two integration
tests that do (`test_ingestion_end_to_end.py`) will self-skip without one, not fail.

If you want the ADR-009 compliance guardrail described in
`docs/PHASE_4_IMPLEMENTATION_PLAN.md` §9 to ever actually engage, you'd explicitly set
`ALLOW_REAL_PHI=true` — until then it's a no-op by default and doesn't affect local dev.

---

## 6. R2 bucket — one real object needed for the load-test script only

`scripts/load_test_ingestion.py` (the Phase 4 done-criteria smoke test) reuses a single real
R2 object for every dispatched document, since it's testing dispatch throughput, not parsing
correctness. Upload any small `.txt` file to
`r2://<R2_DOCUMENT_BUCKET>/seed/load-test/synthetic.txt` once before running it. Nothing else
in this delivery needs a live R2 object — every unit and integration test mocks
`get_object_bytes()`.
