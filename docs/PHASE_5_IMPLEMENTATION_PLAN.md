# Phase 5 — Hugging Face-Hosted Clinical Embedding Server: Implementation Plan

## 0. Where the repo actually stood before this phase

Phase 4 (Core Ingestion Pipeline) was fully merged: `main.py`'s double-yield lifespan bug
fixed, `config.py` merged with Kafka SASL/SSL fields, `MANUAL_INTEGRATION_NOTES.md`'s
action items resolved. `EMBEDDING_PROVIDER` existed in `ingestion/src/config.py` as a config
field but nothing read it — `batch_worker.py` imported `openai_embedder.embed_batch`
directly, hardcoded. `ingestion/embedding-server/` held a parked stub (`Dockerfile` + local
FastAPI `main.py` that returned zero vectors if `Bio_ClinicalBERT` wasn't loadable) —
ADR-009 explicitly deferred completing it past Phase 4.

## 1. The phase-numbering conflict, and what got decided

The project's own docs disagree on what "Phase 5" is:

- The pre-implementation brainstorm tool and docs 01–06/25 define Phase 5 as a
  self-hosted `clinical-bert` FastAPI pod (Docker/K8s).
- `docs/PHASE_4_IMPLEMENTATION_PLAN.md` and `README.md` both internally call the *next*
  phase "Phase 6: Vector Store Layer" — because ADR-011 already pulled a minimal slice of
  it (`upsert()` + `health_check()`) forward into Phase 4, and ADR-009 parked the
  embedding-server phase rather than skipping it outright.

Decision (this session): build the original Phase 5 concept — a self-hosted clinical
embedding server — but change the hosting mechanism from a Docker container we operate to
**Hugging Face Inference Endpoints**, which we don't operate; Hugging Face does. Vector
Store Layer (Weaviate hybrid search completion + Qdrant DR) remains the next phase after
this one, with one decision already banked for it: **dual-write to both Weaviate and
Qdrant on every ingestion upsert**, not a standalone/inactive Qdrant store. See §9.

## 2. Model: not raw `Bio_ClinicalBERT`

Researched current (mid-2026) options rather than assuming the doc-referenced
`emilyalsentzer/Bio_ClinicalBERT` was still the right call. It isn't, for embeddings
specifically — see ADR-012 §1 for the MTEB-style benchmark numbers. Landed on
`NeuML/pubmedbert-base-embeddings`: sentence-transformers-trained specifically for
embeddings, Apache-2.0, 768-dim, and tagged `text-embeddings-inference` on the Hub — which
is what lets Hugging Face's TEI container serve it correctly with zero custom handler code.
`CLINICAL_BERT_MODEL_ID` is a config value, not hardcoded, so this can change later without
a code change.

## 3. Hosting: Inference Endpoints (TEI container), not Docker

`scripts/deploy_hf_embedding_endpoint.py` calls `huggingface_hub.create_inference_endpoint()`
requesting a TEI container. Hugging Face builds, runs, health-checks, and autoscales it —
including scale-to-zero (`min_replica=0` default; ~20–30s cold start on first request after
idle, per HF's own docs — set `HF_ENDPOINT_MIN_REPLICA=1` to keep a warm replica instead).
This is a **manual, outside-of-CI operator step** — it provisions a billed cloud resource,
so it's deliberately not part of `make dev` or any CI job, unlike every other piece of local
infrastructure in this repo.

## 4. New / modified files

### 4.1 `docs/adr/ADR-012-hf-hosted-clinical-bert-embedding-server.md` (new)
Full decision record — model choice reasoning, hosting mechanism, client pattern, provider
routing, the extended BAA guardrail, and the dimension-mismatch constraint.

### 4.2 `ingestion/src/embeddings/clinical_bert_embedder.py` (new)
Mirrors `openai_embedder.py`'s exact shape: lazy `AsyncInferenceClient` construction (same
bug class avoided as Phase 4's `AsyncOpenAI(api_key="")` import-time crash fix), a
`tenacity` retry wrapper gated by a custom `_is_retryable_hf_error()` predicate (retries
`InferenceTimeoutError` and 5xx/429 `HfHubHTTPError`s; does not retry 4xx), and
`embed_batch(texts) -> list[list[float]]`. Sends the whole batch to
`feature_extraction()` in one call per `EMBEDDING_BATCH_SIZE`-sized chunk — TEI pools
server-side and returns one row per input text — rather than one call per text.

### 4.3 `ingestion/src/embeddings/__init__.py` (was empty; now the provider dispatcher)
`embed_batch()` here reads `settings.EMBEDDING_PROVIDER` on every call and routes to
`openai_embedder` or `clinical_bert_embedder`. This is what makes the config field real.

### 4.4 `ingestion/src/workers/batch_worker.py` (one-line change)
`from ..embeddings.openai_embedder import embed_batch` →
`from ..embeddings import embed_batch`. Everything else in that file — retry/DLQ routing,
progress tracking — is untouched Phase 4 code.

### 4.5 `ingestion/src/config.py`
Added `HF_TOKEN`, `HF_EMBEDDING_ENDPOINT_URL`, `HF_EMBEDDING_ENDPOINT_NAME`,
`CLINICAL_BERT_MODEL_ID`, `CLINICAL_BERT_DIMENSIONS`. Retired `EMBEDDING_MODEL_URL`'s
active use (kept as an unused field so a stray `.env` entry doesn't break anything).
Extended `model_post_init`'s PHI guardrail to cover `EMBEDDING_PROVIDER=clinical_bert`,
not just `openai` — see ADR-012 §5 for why a dedicated HF endpoint doesn't get a compliance
pass just for being "dedicated."

### 4.6 `scripts/deploy_hf_embedding_endpoint.py` (new)
`create` / `status` / `pause` / `resume` / `delete` subcommands. `create` is idempotent —
reuses an existing endpoint of the same name instead of erroring.

### 4.7 `ingestion/embedding-server/` retired
`Dockerfile` and `requirements.txt` deleted; local `main.py` deleted (still visible via
`git log --follow` on that path). Replaced with a `README.md` pointer explaining the pivot.
`docker-compose.yml`'s `embedding-model` service removed. `.github/workflows/deploy.yml`'s
`pvh-embedding` image build/push removed. `Makefile`, `scripts/dev.ps1`, `scripts/dev.bat`
status output and `dev-lite` messaging updated to stop referencing `localhost:8001`.

### 4.8 `ingestion/requirements.txt`
Added `huggingface_hub>=1.24.0,<1.25.0` (current as of this build — see Footnotes).

### 4.9 `.env.example`, `.env.example.cloud`
New `HF_TOKEN` / `HF_EMBEDDING_ENDPOINT_URL` / `HF_EMBEDDING_ENDPOINT_NAME` /
`CLINICAL_BERT_MODEL_ID` / `CLINICAL_BERT_DIMENSIONS` block, plus `ALLOW_REAL_PHI` /
`PHI_BAA_ACKNOWLEDGED` surfaced explicitly (they existed in `config.py` since Phase 4 but
were never documented in either `.env.example` file).

### 4.10 `.github/workflows/ci.yml`
`huggingface_hub` added to the `test-unit` job's pip install (new test files import it
directly — same "fails to *collect*, not just fails" reasoning already documented inline
for `weaviate-client`/`qdrant-client`). Added a fake `HF_TOKEN` test env var alongside the
existing fake `OPENAI_API_KEY`.

### 4.11 `README.md`
Service map row, venv notes, and the Ingestion section's embedding config example all
updated to describe both providers and stop describing embedding as a local port.

### 4.12 Tests (new)
- `tests/unit/test_clinical_bert_embedder.py` — batching, ordering, empty-input short
  circuit, single-call-per-batch (not per-text), `normalize=True` passthrough, retry-on-
  `InferenceTimeoutError`, lazy client construction, and `_is_retryable_hf_error()`'s
  5xx/429-retryable vs. 4xx-not-retryable branches (via `MagicMock(spec=HfHubHTTPError)` —
  avoids depending on that class's exact constructor signature, which differs across
  `huggingface_hub` versions).
- `tests/unit/test_embeddings_provider_routing.py` — `EMBEDDING_PROVIDER=openai` routes to
  `openai_embedder`, `=clinical_bert` routes to `clinical_bert_embedder`, an unknown value
  raises `ValueError`, and the shipped default is still `openai`.

## 5. Build sequence

1. ADR-012 first — the model/hosting/compliance decisions the rest of the code depends on.
2. `clinical_bert_embedder.py` — the piece every other change routes to.
3. `embeddings/__init__.py` dispatcher, then the one-line `batch_worker.py` change.
4. `config.py` fields + guardrail extension.
5. `deploy_hf_embedding_endpoint.py` — the operator-facing provisioning tool.
6. Retire `ingestion/embedding-server/`'s Docker path; update every file that referenced it
   (`docker-compose.yml`, `deploy.yml`, `Makefile`, `dev.ps1`, `dev.bat`, `README.md`).
7. `requirements.txt`, `.env.example*`, `ci.yml`.
8. Tests.

## 6. Testing plan

Same posture as Phase 4: the Hugging Face client is always mocked in unit tests — no
`HF_TOKEN`, no deployed endpoint, no network call required to run `pytest tests/unit/`.
`_is_retryable_hf_error()` is tested directly as a pure predicate rather than trying to
construct real `HfHubHTTPError` instances with genuine HTTP response objects, since that
class's constructor signature isn't stable across `huggingface_hub` versions and the goal
is testing *our* branching logic, not the library's exception internals.

There is deliberately no integration test that calls a real Hugging Face endpoint — same
reasoning as Phase 4's "mock boto3 entirely in CI" decision, extended to this new external
dependency.

## 7. Definition of Done

- [x] `clinical_bert_embedder.py` implements `embed_batch()` against the documented
      `AsyncInferenceClient.feature_extraction()` API, retrying transient failures only.
- [x] `EMBEDDING_PROVIDER` actually controls which embedder runs (it didn't before).
- [x] `batch_worker.py`'s only change is the import line — no behavior change to retry/DLQ
      logic that Phase 4 already tested.
- [x] PHI guardrail covers both providers.
- [x] No Docker image, Dockerfile, or local container involved in the clinical embedding
      path anywhere in the repo.
- [x] Every file that referenced the old local embedding-server port or image is updated,
      not just the embedder module itself.
- [x] Unit tests pass without real credentials or network access.

## 8. Compliance guardrail (ADR-009 extended by ADR-012 — don't skip this)

Neither embedding provider is "self-hosted" in the sense the original Phase 5 plan meant
(our own VPC). Both are accepted for synthetic-data development only. `ALLOW_REAL_PHI=true`
without `PHI_BAA_ACKNOWLEDGED=true` refuses to boot regardless of `EMBEDDING_PROVIDER`.

## 9. Open decisions — resolved this session, recorded here for Phase 6

Two decisions were made together at the start of this phase, in one round:

1. **This phase's scope**: self-hosted clinical-bert embedding server, Hugging
   Face-hosted rather than Docker-hosted. (Built — this document.)
2. **Phase 6 (Vector Store Layer) Qdrant scope, decided now for later**: dual-write to
   both Weaviate and Qdrant on every ingestion upsert, not a standalone/inactive Qdrant
   store activated only on failover. This is **not implemented in this phase** —
   `QdrantStore` still doesn't exist, `WeaviateStore.search()`/`.delete()` still raise
   `NotImplementedError`. It's recorded here so Phase 6 starts from a decided design
   instead of re-litigating it.

## 10. Risk carryover + one new risk

- Carried from Phase 4 / the original risk register: "clinical-bert pod slow to start" is
  resolved by construction — there's no pod we boot. TEI's own cold-start (scale-to-zero
  case) is now Hugging Face's problem, bounded to ~20–30s per their docs, and avoidable
  entirely with `HF_ENDPOINT_MIN_REPLICA=1`.
- New risk: `scripts/deploy_hf_embedding_endpoint.py create` is a manual step outside CI/CD.
  If `EMBEDDING_PROVIDER=clinical_bert` is set without first running it,
  `HF_EMBEDDING_ENDPOINT_URL` is empty and the first real ingestion call fails loudly (by
  design — see `config.py`'s comment on that field) rather than silently talking to
  nothing. Not auto-remediated; an operator has to run the script.
- New risk: a second external-service failure domain. `clinical_bert_embedder.py`'s retry
  wrapper covers transient failures (503 cold-start-adjacent, 429, other 5xx); it does not
  cover an extended Hugging Face outage. Same class of risk the `openai` provider already
  carries for OpenAI's uptime — not a regression, just now present twice.

## Footnotes (verified July 2026)

1. `weaviate-client` current PyPI release is `4.21.1`; this repo's pin
   (`>=4.20.4,<4.21.0`) is one minor version behind but within a supported range — no forced
   bump for this phase, since Vector Store Layer work (Phase 6) is the natural point to
   re-verify against whichever client version is current then.
2. `qdrant-client` current PyPI release is `1.18.0`, matching this repo's existing pin
   exactly — no change needed.
3. `huggingface_hub` is at a major version bump, `1.24.0` (the `0.x` series is EOL) —
   confirmed `InferenceClient`/`AsyncInferenceClient`, `feature_extraction()`,
   `create_inference_endpoint()`, and the `errors.InferenceTimeoutError` /
   `errors.HfHubHTTPError` exception classes used in this phase are all present and
   documented as of `1.x` (internal transport moved from `requests`/`aiohttp` to `httpx`,
   which doesn't change any of the call signatures this code depends on). Requires Python
   `>=3.10`; this repo targets `3.11`, so no conflict.
4. `NeuML/pubmedbert-base-embeddings` model card confirms: `sentence-transformers` +
   `text-embeddings-inference` tags present, Apache-2.0 license, 768-dim output. A
   Matryoshka variant (`-matryoshka`, dynamic 64–768 dim) exists if a smaller footprint is
   wanted later — not used here; `CLINICAL_BERT_DIMENSIONS=768` assumes the base model.
