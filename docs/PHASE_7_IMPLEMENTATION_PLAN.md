# Phase 7 Implementation Plan — RAG Query Engine

## Scope

Everything between "an analyst submits a query" and "a cited answer
comes back over HTTP": query embedding, retrieval, LLM synthesis, and
`POST /v1/query`. Confirmed against ADR-013 §1 ("Phase 7 is the first
caller of `search()`") and against this repo's own precedent for router
mounting before writing any code — see `docs/adr/ADR-014-rag-query-
engine.md` for the three decisions that needed confirming up front
(mount timing, whether to build a separate BM25/RRF layer on top of
Phase 6's native hybrid search, and the default model) and the reasoning
behind each.

## Files delivered

**New:**
- `rag-engine/src/query_embedder.py` — embeds query text (OpenAI default
  / clinical_bert alternate), duplicated rather than imported from
  ingestion's embedders (ADR-014 §1).
- `rag-engine/src/retriever.py` — the caller ADR-013 §1 named.
- `rag-engine/src/llm_router.py` — Anthropic (default) / OpenAI /
  Gemini, all three client-construction behaviors and call shapes
  verified against the actually-installed SDKs (`anthropic==0.120.2`,
  `openai==2.50.0`, `google-genai==2.14.0`).
- `rag-engine/src/synthesizer.py` — prompt + citation extraction.
- `rag-engine/requirements.txt` — recreated; the original came through
  unreadable in the repo dump (`[Binary file]`), same issue Phase 4 hit
  with `main.py`/`config.py`. Safe to recreate fresh since it's a new
  file with no prior content to reconcile against.
- `api-gateway/src/routers/query.py` — `POST /v1/query`.
- `api-gateway/src/schemas/query.py` — request/response models.
- `tests/unit/test_query_embedder.py`, `test_llm_router.py`,
  `test_rag_synthesizer.py`, `test_retriever.py`, `test_query_router.py`
  — 44 tests total for this phase, all passing against this project's
  actual `pyproject.toml` (`ruff check .`, `ruff format --check .`,
  `mypy --config-file pyproject.toml`, all clean).
- `tests/integration/test_rag_query_pipeline.py` — live-service tests,
  self-skipping without real API keys (matching
  `test_ingestion_end_to_end.py`'s established pattern):
  `TestRAGSynthesizerLive` needs only `ANTHROPIC_API_KEY` and proves
  `messages.create()`'s real call shape/response parsing — the single
  highest-value previously-unverified surface this phase introduces, no
  existing test calls a real LLM completion API at all.
  `TestFullQueryPipelineLive` needs both `ANTHROPIC_API_KEY` and
  `OPENAI_API_KEY` and proves `retrieve()` end to end against a real
  Weaviate-stored chunk.
- `docs/adr/ADR-014-rag-query-engine.md`.

**Edited:**
- `api-gateway/src/main.py` — query router mounted (see ADR-014 for why
  this phase, not a later one).
- `rag-engine/src/config.py` — added `HF_TOKEN` /
  `HF_EMBEDDING_ENDPOINT_URL` / `CLINICAL_BERT_MODEL_ID` /
  `CLINICAL_BERT_DIMENSIONS` (query_embedder.py's clinical_bert path
  needs the same fields ingestion's config already carries),
  `LLM_ANTHROPIC_MODEL` / `LLM_OPENAI_MODEL` / `LLM_GEMINI_MODEL`, and
  the `ALLOW_REAL_PHI` / `PHI_BAA_ACKNOWLEDGED` guardrail mirrored from
  `ingestion/src/config.py` — query_embedder.py sends the analyst's free
  -text query to the same third-party providers ingestion's document
  embedder does, and nothing about being on the query path makes that
  PHI-egress concern go away.
- `vector-store/src/weaviate_store.py` — `search()` now runs the sync
  `weaviate-client` call via `asyncio.to_thread()`, closing the gap
  Phase 6's own docstring explicitly deferred to "when Phase 7's query
  latency makes it worth it." Scoped to `search()` only; verified
  non-regression by re-running Phase 6's existing
  `test_weaviate_search_delete.py` against the change (passes
  unchanged).
- `api-gateway/Dockerfile` — repo-root build context (was
  `api-gateway/` alone), now installs and copies in `rag-engine` and
  `vector-store` too, matching `ingestion/Dockerfile`'s existing shape.
- `.github/workflows/ci.yml` — `anthropic`/`google-genai` added to
  `test-unit` and `test-integration`'s installs (needed for these new
  test files to *collect*, not just pass — same "fails to collect, not
  just fails" class of problem as every other SDK already on that list);
  fake `ANTHROPIC_API_KEY`/`GEMINI_API_KEY` added to `test-unit`'s env;
  `security-scan`'s `pvh-api` build fixed to repo-root context.
- `.github/workflows/deploy.yml` — **both** `pvh-api` and `pvh-workers`
  build-context bug fixed. The `pvh-workers` (ingestion) half of this
  was a pre-existing bug, not something this phase introduced — caught
  by reading this file's actual current content while touching it for
  the `pvh-api` half, the same "validate against actual repo dumps"
  practice that caught the original version of this exact bug in
  Phase 4.
- `tests/conftest.py` — `"rag-engine"` added to `subproject_names`;
  `_ensure_cross_package_alias()` added so `vector_store`/`rag_engine`
  resolve as top-level cross-package imports during tests — see
  ADR-014's "Testing consequence" section for why this was a
  previously-latent gap this phase's own tests are the first to expose.
- `docs/MANUAL_INTEGRATION_NOTES.md` — Phase 4 items marked resolved
  (verified against the current file contents — `main.py` and
  `config.py` are no longer binary in this dump, both fully readable and
  correct); Phase 7's own new items added.

## Decisions confirmed before implementation

See `docs/adr/ADR-014-rag-query-engine.md`'s "Decisions confirmed before
implementation" section — router-mounting timing, BM25/RRF scope, and
default model were all confirmed rather than assumed before writing any
Phase 7 code.

## Bugs / gaps caught during implementation

(Same "verify against real library behavior, not just syntax" standard
this project has held since Phase 4.)

1. **`weaviate_store.py`'s `search()` blocking the event loop** —
   already flagged by Phase 6's own docstring as a "revisit in Phase 7"
   item; fixed here (`asyncio.to_thread()`), not just re-flagged.
2. **`deploy.yml`'s build-context bug, still present for `pvh-workers`**
   — a pre-existing bug independent of this phase's changes, caught
   while editing this file for the `pvh-api` half.
3. **`ci.yml`'s `security-scan` job building `pvh-api` from the wrong
   context** — same root cause as #2, different file; fixed alongside
   the `Dockerfile` change that made it matter.
4. **A previously-latent test-collection gap** — no unit test before
   this phase needed `vector_store` resolvable as a top-level
   cross-package import; this phase's own new tests are the first to
   need it, and would fail to collect without `tests/conftest.py`'s new
   `_ensure_cross_package_alias()`.
5. **`openai`'s `message.content` is `str | None`, not always `str`** —
   caught by `mypy`'s `warn_return_any` (enabled in this project's
   `pyproject.toml`), not by inspection; a tool-call-only response would
   otherwise have silently produced a `None` answer three layers up in
   `synthesizer.py`. Now raises a clear error instead.
6. **`huggingface_hub` has released past `ingestion/requirements.txt`'s
   existing `<1.25.0` ceiling** (currently at 1.25.1) — noted, not
   changed; `rag-engine/requirements.txt`'s new pin was kept at the same
   already-tested ceiling for consistency rather than adopting a newer
   minor version unilaterally. Bump both together if this is revisited.
7. **`openai` itself has released a new major version** (2.50.0, vs.
   ingestion's existing `<2.0.0` pin) — noted, not changed, for the same
   reason: `rag-engine/requirements.txt` matches ingestion's existing,
   already-tested `openai` pin rather than introducing an unverified
   major-version jump as part of this phase.

## Files needing manual verification

Three files came through unreadable (`[Binary file]`) in the repo dump
used for this phase, same issue Phase 4 hit originally:

- `rag-engine/requirements.txt` — recreated fresh (new file, nothing to
  reconcile against).
- `api-gateway/src/errors.py` — **not** recreated. Its contract was
  fully recovered from `tests/unit/test_errors.py` (which already
  covers `QueryError`/`LLMError`, apparently provisioned ahead of this
  phase), which was sufficient to use it correctly in
  `routers/query.py` without needing to guess at or reconstruct its
  actual source. If you have the real file, no action needed — nothing
  in this phase's delivery assumes anything about it beyond what the
  test file already proves.
- `Makefile` — not touched; nothing in this phase requires a Makefile
  change. Left exactly as-is.

## Testing

44 unit tests (all passing), 2 integration test classes (self-skip
without real API keys — see "Files delivered" above), against this
project's actual `pyproject.toml`:
- `ruff check .` — clean.
- `ruff format --check .` — clean.
- `mypy api-gateway/src ingestion/src rag-engine/src vector-store/src
  --ignore-missing-imports` — clean for every file this phase touched.
- Re-ran Phase 6's existing `test_weaviate_search_delete.py` against the
  modified `weaviate_store.py` — passes unchanged (concrete
  non-regression check, not just reasoning about it).

## What's NOT in this phase

- A standalone BM25/RRF layer — deliberately scoped out; see ADR-014 §2.
- Query result caching (Redis is available, currently only used as the
  Celery broker) — no existing requirement calls for it; revisit if
  repeated-identical-query load ever makes it worth the added
  invalidation complexity.
- `date_range` / `cohort_filter` on `QueryRequest.filters` — the
  original doc-32 sketch included them, but `vector-store/src/
  weaviate_store.py`'s `_build_filter()` only implements
  `document_types` today. `QueryRequest`'s schema matches what the
  storage layer can actually honor rather than exposing filters that
  would silently no-op.
- `/v1/audit` — genuinely later-phase (compliance work), left commented
  in `main.py` exactly where it was.
- Rate limiting, response caching, or any Kong/gateway-level concern for
  `/v1/query` specifically — that's Phase 8+ territory per the original
  "REST API & Gateway" phase scope, unaffected by this phase's decision
  to mount the route itself now.

## On the horizon

- Phase 8 and beyond per the existing phased plan — `/v1/audit`,
  gateway-level rate limiting, frontend query UI, observability.
- If DR failover to Qdrant-primary ever becomes a real operational
  concern, revisit whether a standalone BM25 index (scoped out this
  phase — ADR-014 §2) is worth building for that mode specifically.
- `api-gateway`'s image is meaningfully heavier now (transitively
  carries `anthropic`, `google-genai`, `weaviate-client`,
  `qdrant-client`) — not addressed this phase, worth revisiting if
  build time or image size becomes a real problem.
