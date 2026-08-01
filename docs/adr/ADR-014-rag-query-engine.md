# ADR-014: RAG Query Engine — retrieval, synthesis, and the /v1/query route

**Status:** Accepted
**Date:** Phase 7
**Deciders:** Engineering (confirmed with product owner on scope/model
defaults before implementation — see "Decisions confirmed before
implementation" below)

## Context

ADR-013 (Phase 6) added `query_vector` to `VectorStoreInterface.search()`
and explicitly named Phase 7 as its first caller. Phase 7's job is
everything between "an analyst types a question" and "a cited answer
comes back": embedding the query, retrieving chunks, synthesizing an
answer, and exposing all of it as `POST /v1/query`.

Three things needed deciding before writing any of that, because getting
them wrong would mean redoing real work, not just a naming nit:

1. Does this phase mount the HTTP route, or just build rag-engine's
   internals and leave `main.py` untouched?
2. Do we build the separate BM25 + Reciprocal Rank Fusion layer the
   original design docs (doc-22) sketched, on top of what Phase 6
   already shipped?
3. What LLM and model default?

## Decisions confirmed before implementation

**1. Mount `/v1/query` in `main.py` this phase.** `main.py` had a stale
comment bundling `query` in with `audit` under "Phase 8+ routers" — but
nothing in this codebase has ever deferred a router's HTTP mounting to a
later phase than the one that built it (`admin_router` mounted in
Phase 3, `ingest_router_module.router` in Phase 4). `audit` genuinely is
later-phase (compliance work); `query` was not, and ADR-013 §1's own
language ("Phase 7 is the first caller") only makes sense if Phase 7
actually calls it. Confirmed rather than assumed.

**2. No separate BM25/RRF layer.** `WeaviateStore.search()` (Phase 6)
already does native hybrid search — BM25 + vector, fused server-side via
`.query.hybrid()` — for the default (Weaviate-primary) path. The
original doc-22 design predates that; it assumed a Redis-backed
`BM25Okapi` index rebuilt on a Celery-beat schedule, fused client-side
via Reciprocal Rank Fusion against Weaviate's dense-only results. That
would be solving a problem Phase 6 already solved, at the cost of a
second index to keep in sync and a new scheduled job. The one place a
separate BM25 index would still earn its keep — Qdrant has no keyword
signal at all, so a Qdrant-primary DR failover loses BM25 entirely — is
a real gap, but it's a DR-mode gap, not a default-path one; revisit if
DR failover ever actually needs it, rather than building it speculatively
now.

**3. `claude-sonnet-5` as the default model**, balancing cost against
answer quality for a retrieval-grounded clinical-document synthesis task
— not the cheapest (`claude-haiku-4-5`) or the highest-quality/priciest
(`claude-opus-4-8`) option. `LLM_DEFAULT_PROVIDER=anthropic` was already
set in `rag-engine/src/config.py` before this phase; this decision was
just the model tier within that provider.

## Decision

- `rag-engine/src/query_embedder.py` — embeds the query text.
  Duplicates `ingestion/src/embeddings/{openai_embedder,
  clinical_bert_embedder}.py`'s client-construction and retry logic
  rather than importing them. Importing ingestion's embedder would
  invert the dependency direction the same way ADR-013 §1 already
  rejected for `vector_store` — for the same reason (ingestion pulls in
  boto3, PyMuPDF, python-hl7, and Celery, none of which the query path
  needs, and a change to ingestion's batch-embedding internals shouldn't
  be able to break query serving).
- `rag-engine/src/retriever.py` — embeds the query, calls
  `vector_store.interface.get_store(tenant_id).search(...)`. This is the
  caller ADR-013 §1 named.
- `rag-engine/src/llm_router.py` — Anthropic (default) / OpenAI / Gemini,
  each with a lazily-constructed client (see "Client construction
  behavior" below) and provider-specific retry on transient errors.
- `rag-engine/src/synthesizer.py` — builds the grounding prompt, extracts
  `[n]`-style citations from the answer. Short-circuits without an LLM
  call when retrieval returns zero chunks.
- `api-gateway/src/routers/query.py` — `POST /v1/query`,
  `require_min_role("analyst")` (matches doc-09's original API
  contract), writes `query_logs` (via `crud.log_query` — present in
  `db/crud.py` since Phase 4/6, unused until now) and `audit_logs`
  (`action="document_query"`, matching `ingest.py`'s existing
  `document_ingest` pattern exactly). Retrieval/synthesis failures are
  wrapped in `errors.py`'s existing `QueryError`/`LLMError` — see
  "Errors.py" below.

## Client construction behavior (verified against installed SDKs)

Same "verify against real library behavior, not just docs" practice
this project has followed since Phase 4 (the `AsyncOpenAI`,
`AIOKafkaProducer`, `boto3` findings) — installed and exercised each SDK
rather than assuming from documentation:

| Provider | Package (installed) | `Client(api_key="")` at construction | Fix |
|---|---|---|---|
| Anthropic | `anthropic==0.120.2` | Does **not** raise | `or "not-configured"` anyway, for consistency across all three providers and defensiveness against a future SDK release adding the same eager validation OpenAI's already has |
| OpenAI | `openai==2.50.0` | **Raises** `OpenAIError` ("Missing credentials...") | `or "not-configured"` — same fix `openai_embedder.py` already needed |
| Gemini | `google-genai==2.14.0` | **Raises** `ValueError` | `or "not-configured"` |

All three provider clients in `llm_router.py` and both embedder paths in
`query_embedder.py` use lazy construction (`_get_*_client()` functions,
`None`-checked module globals) — importing either module can never
crash on a missing API key, only calling it does.

Async call shapes, also verified against the installed SDKs, not
assumed:
- Anthropic: `await client.messages.create(model=, max_tokens=,
  messages=[...])` → `message.content[0].text`
- OpenAI: `await client.chat.completions.create(model=, max_tokens=,
  messages=[...])` → `response.choices[0].message.content` (typed
  `str | None` — a tool-call-only response would otherwise silently
  become a `None` answer three layers up in `synthesizer.py`; this now
  raises instead)
- Gemini: `await client.aio.models.generate_content(model=, contents=,
  config=types.GenerateContentConfig(max_output_tokens=...))` →
  `response.text`. Exceptions live in `google.genai.errors` —
  `ServerError` (5xx) and `ClientError` with `.code == 429` are the ones
  worth retrying; other 4xx `ClientError`s won't succeed on retry.

## errors.py

`api-gateway/src/errors.py`'s own source came through unreadable in the
repo dump — same issue Phase 4 hit with `main.py` and `config.py` (see
`MANUAL_INTEGRATION_NOTES.md`). Its contract was recovered from
`tests/unit/test_errors.py`, which already exercises a full hierarchy
including `QueryError` (status 500, `"QUERY_ERROR"`) and `LLMError`
(status 503, `"LLM_ERROR"`) — both apparently provisioned in advance of
this phase, since nothing before Phase 7 used either. `routers/query.py`
wraps retrieval failures in `QueryError` and synthesis failures in
`LLMError`, giving a Weaviate outage and an Anthropic outage distinct,
structured error codes instead of both collapsing into the same
unstructured 500 an unhandled exception would produce.

## Consequence: cross-package imports reach api-gateway for the first time

`routers/query.py` imports `rag_engine.retriever` and
`rag_engine.synthesizer` directly, which themselves import
`vector_store.interface` — the same in-process cross-package pattern
`ingestion/src/workers/batch_worker.py` has used since Phase 4, now
reaching `api-gateway` for the first time. Mechanically:

- `api-gateway/Dockerfile` moved to repo-root build context (was
  `api-gateway/` alone), now also installs `rag-engine/requirements.txt`
  and `vector-store/requirements.txt` and copies both `src/` trees in
  under the module names those imports expect (`rag_engine`,
  `vector_store`) — identical shape to what `ingestion/Dockerfile`
  already does.
- `.github/workflows/ci.yml`'s `security-scan` job built `pvh-api` from
  the wrong context (`api-gateway/` instead of repo root); fixed
  alongside the Dockerfile change, matching how `pvh-ingestion` was
  already built correctly there.
- `.github/workflows/deploy.yml` had the **same** bug for **both**
  images (`pvh-api` and `pvh-workers`), still present as of this phase
  despite `pvh-ingestion` having been built correctly in `ci.yml` since
  Phase 4 — this file just hadn't been brought in line. Fixed both while
  touching this file for the `pvh-api` change anyway; caught the same
  way the original version of this bug was caught in Phase 4
  ("Validate against actual repo dumps" — reading this file's actual
  current content rather than assuming an earlier fix had landed here).
- `tests/conftest.py` gained `_ensure_cross_package_alias()` — see
  "Testing consequence" below.
- `MANUAL_INTEGRATION_NOTES.md` gained the equivalent local (non-Docker)
  dev step.

## Testing consequence: a previously-latent gap in the test harness

No existing unit test imports `vector_store` as a top-level cross-package
name — every existing reference to it (`test_weaviate_search_delete.py`,
`test_qdrant_store.py`, `test_dual_write_store.py`) imports it via its
own subproject's `sys.path.insert()` + `from src.X import Y` convention,
staying entirely inside the `vector-store` subproject's own namespace.
`ingestion/src/workers/batch_worker.py` does cross-import it, but has no
dedicated unit test, so nothing before this phase ever exercised the
cross-import at collection time — only Docker-built integration
environments did.

`rag-engine/src/retriever.py` and `synthesizer.py` both do
`from vector_store.interface import ...` at module level — their entire
job is calling into `vector_store` — and `api-gateway/src/routers/
query.py` does the same for `rag_engine`. This is the first phase where
a *unit* test needs a cross-subproject top-level import to resolve, not
just a Docker-built integration environment. Left alone, `tests/unit/
test_retriever.py`, `test_rag_synthesizer.py`, and `test_query_router.py`
would fail to *collect* — which fails the entire `pytest` run, not just
those files.

Fixed in `tests/conftest.py` with `_ensure_cross_package_alias()`: makes
`vector-store/src` and `rag-engine/src` importable as the top-level
`vector_store` / `rag_engine` names via `importlib.util.spec_from_file_
location()`, without needing a symlink, a copy step, or a `pip install
-e` (`vector-store` still has no `setup.py`/`pyproject.toml` of its own
— see `MANUAL_INTEGRATION_NOTES.md`'s Phase 4 note, still open).
Idempotent and cheap, so it runs unconditionally in `pytest_runtest_
setup` rather than only for test files known in advance to need it.

As a side effect, this also resolves the concern `docs/PHASE_6_
IMPLEMENTATION_PLAN.md` raised about not mixing multiple subprojects'
`sys.path` in one integration test file — `tests/integration/
test_rag_query_pipeline.py` needs `rag-engine`'s own convention *and*
`vector_store` resolvable, and now can have both.

## vector-store/src/weaviate_store.py: search() now runs off the event loop

`weaviate-client` v4 has no fully async surface; Phase 6's own docstring
already flagged that calling it directly from `async def` blocks the
event loop for the call's duration, and explicitly deferred fixing it:
*"revisit if/when Phase 7's query latency makes it worth wrapping in a
thread executor."* That was an acceptable trade when the only call site
was Celery background workers (Phase 4) and the dual-write addition
(Phase 6) — not interactively latency-sensitive. Phase 7 puts this
exact code on the hot path of every `/v1/query` HTTP request, where a
blocked event loop stalls every other in-flight request on the same
worker process, so this phase does the deferred fix: `search()` now runs
the sync `weaviate-client` call via `asyncio.to_thread()`.

Scoped to `search()` only — `upsert()`/`delete()`/`health_check()` stay
exactly as they were. They're still Celery/background-only call sites,
already tested across Phases 4 and 6; touching them would be changing
already-verified code for no behavioral reason connected to this phase.
Verified non-regression concretely, not just by inspection: re-ran the
existing `tests/unit/test_weaviate_search_delete.py` (Phase 6) against
the modified file — passes unchanged, since `asyncio.to_thread()` still
invokes the same call with the same arguments, just off the event loop;
a `MagicMock`-based test can't observe the difference.

## Consequences

- `/v1/query` is live and end-to-end testable via HTTP, matching this
  phase's own precedent for router mounting.
- Retrieval quality depends entirely on Weaviate's native hybrid search;
  no independent keyword index exists outside of it. Acceptable given
  the primary path's coverage; the Qdrant-DR gap this leaves is tracked,
  not solved, here.
- `api-gateway` now carries `anthropic`, `google-genai`,
  `weaviate-client`, and `qdrant-client` as transitive dependencies via
  `rag-engine`/`vector-store`'s requirements files — a meaningfully
  heavier image than before this phase. Not addressed in this ADR;
  worth revisiting if image size/build time becomes a real problem.
- `rag-engine/requirements.txt` and `api-gateway/src/errors.py` remain
  two of the files that came through unreadable in the repo dump.
  `requirements.txt` was safe to recreate fresh (new file, no prior
  content to preserve). `errors.py` was not touched — its contract was
  recovered from its test file, which was enough to use it correctly
  without needing to reconstruct or guess at its exact source.
