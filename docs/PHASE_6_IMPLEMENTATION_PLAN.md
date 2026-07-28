# Phase 6 — Vector Store Layer Completion: Implementation Plan

## 0. Where the repo stood before this phase

Phase 5 (ADR-012) shipped clean. `WeaviateStore.upsert()` and `.health_check()` were real
(ADR-011, pulled into Phase 4); `.search()` and `.delete()` raised `NotImplementedError`;
`QdrantStore` didn't exist; `get_store()` always returned a bare `WeaviateStore`. Two
decisions were banked from the start of Phase 5's session for this phase: dual-write to both
Weaviate and Qdrant on every ingestion upsert (not a standalone/inactive Qdrant store).

## 1. The `query_vector` interface change (ADR-013 §1)

Implementing `search()` for real surfaced a real problem, not a stylistic one: the
`PatientDocument` Weaviate collection uses self-provided vectors (ADR-009 — no server-side
vectorizer), so hybrid search needs an explicit query *vector* for its dense half, not just
query text. Qdrant has no BM25 at all — it's unconditionally vector-only. Embedding the query
text requires an embedder, and embedders live in `ingestion/src/embeddings/`. Rather than
having `vector_store` import from `ingestion` (inverting the dependency Phase 4 established
and making the two packages circular), `search()`'s signature grew a required
`query_vector: list[float]` parameter — the caller embeds the query text itself. There's no
caller yet (Phase 7 is the first), so this is a clean signature change.

## 2. What got built

- **`vector-store/src/weaviate_store.py`**: `search()` — native `.query.hybrid(query=...,
  vector=..., alpha=0.5, filters=..., return_metadata=MetadataQuery(score=True))`, verified
  against the installed `weaviate-client` docs/examples for the bring-your-own-vector
  pattern. `delete()` — `collection.data.delete_many(where=Filter.by_property("document_id")
  .equal(doc_id))` on the tenant-scoped collection.
- **`vector-store/src/qdrant_store.py`** (new): full `VectorStoreInterface` implementation.
  Per-tenant collections (`patient_docs_{tenant_id}`, matching the existing setup script).
  Uses `AsyncQdrantClient.query_points()` — confirmed via direct introspection of the
  installed `1.18.0` client that `.search()`/`.search_batch()` are deprecated in favor of
  this universal endpoint. `upsert()` with `wait=False` (background indexing — acceptable
  since this is the DR/secondary target). Deterministic point IDs
  (`uuid5(NAMESPACE_DNS, f"qdrant:{doc_id}:{index}")`) for idempotent re-processing, same
  property as Weaviate's chunk UUIDs (different namespace tag, not literally the same ID).
- **`vector-store/src/dual_write_store.py`** (new): `DualWriteVectorStore` wraps a primary
  and secondary store. `upsert()`/`delete()` fan out to both; primary failure raises
  (preserves `batch_worker.py`'s Phase 4 retry/DLQ behavior untouched), secondary failure is
  logged and swallowed (a lagging DR copy beats failing ingestion over the backup target).
  `search()`/`health_check()` read from the primary only.
- **`vector-store/src/interface.py`**: `get_store()` now returns `DualWriteVectorStore`
  (Weaviate primary, Qdrant secondary) when `VECTOR_BACKEND=weaviate` (default), or a bare
  `QdrantStore` when `VECTOR_BACKEND=qdrant` (manual DR failover — new writes shouldn't keep
  targeting a presumably-down Weaviate). **Zero changes to `batch_worker.py`** — the
  dual-write policy is entirely inside what `get_store()` returns.
- **Dimension-aware Qdrant schema** (ADR-012's flagged gap, resolved here):
  `vector-store/src/config.py` gained `CLINICAL_BERT_DIMENSIONS`; `scripts/
  setup_qdrant_schema.py` now picks `EMBEDDING_DIMENSIONS` or `CLINICAL_BERT_DIMENSIONS`
  based on `EMBEDDING_PROVIDER` instead of always assuming OpenAI's 1536.
- **`QDRANT_PORT` default bug, found and fixed**: every service config and `.env.example`
  defaulted to `6334` (Qdrant's gRPC port) where the REST client's `port=` kwarg needed
  `6333`. Latent since nothing ever actually connected to Qdrant before this phase — fixed
  in `vector-store/`, `ingestion/`, `api-gateway/`, `rag-engine/`'s configs and both env
  example files. See ADR-013 §5.
- **Tests**: `test_weaviate_search_delete.py`, `test_qdrant_store.py`,
  `test_dual_write_store.py`, `test_vector_store_factory.py` (all unit, mocked clients) and
  `tests/integration/test_vector_store_layer.py` (new — live Weaviate + live Qdrant, a fixed
  fake vector instead of a real embedder, proves upsert/search/delete and the dual-write
  fan-out actually work against real services).
- **CI**: a `qdrant:` service added to the integration job (mirroring the existing
  `weaviate:` one), `qdrant-client` added to that job's pip install, a Qdrant collection
  setup step, and `QDRANT_HOST`/`QDRANT_PORT` added to the test-run env.

## 3. A pre-existing bug this phase's testing work surfaced (not fixed here)

Writing `tests/integration/test_vector_store_layer.py`, I went to extend the existing
`tests/integration/test_ingestion_end_to_end.py` to also assert `search()` found what
`process_document()` upserted. That file does two `sys.path.insert(0, ...)` calls — one for
`ingestion`, one for `vector-store` — and **both directories contain a package literally
named `src`**. Regular Python packages (these have non-empty-looking but actually empty
`__init__.py` files, i.e. real packages, not namespace packages) resolve from whichever
`sys.path` entry is found first and do not merge with same-named packages elsewhere on the
path. I confirmed empirically (a plain Python process, no test framework involved) that
`from src.workers.batch_worker import ...` fails with `ModuleNotFoundError: No module named
'src.workers'` using that file's own two path inserts — reproduced identically on a clean,
unmodified checkout, so this is not something Phase 5 or 6 introduced. This is the same root
cause as the cross-service pytest/mypy collision flagged at the end of Phase 5, but concretely
worse than I'd realized then: it breaks this one file **standalone**, not just in combination
with other test files.

I did not fix this — it's a cross-cutting packaging decision (four services all named `src`)
that affects every test file using this pattern, not something to fold into a Vector Store
Layer diff. Instead, `test_vector_store_layer.py` is scoped to `vector-store` only, sidestepping
the collision entirely, which is arguably the more direct way to test the storage layer
regardless. Flagged again here, more concretely, for whenever it's worth a dedicated fix.

## 4. Testing plan

Same posture as Phase 4/5 for unit tests: every client (`weaviate`, `qdrant_client`) is
mocked; no live service needed to run `tests/unit/`. Verified the actual API shapes by
introspecting the installed `weaviate-client` (4.20.4) and `qdrant-client` (1.18.0) packages
directly — e.g. confirming `AsyncQdrantClient.query_points`'s real signature, not just
trusting documentation snippets — before writing code against them.

Unlike Phase 4/5, this phase adds a genuine **live-service** integration test
(`test_vector_store_layer.py`) against real Weaviate and Qdrant CI services. Justification:
API-shape correctness here (the exact `query=`/`vector=` combination Weaviate's hybrid search
needs; `query_points()` vs. the deprecated `search()`) is exactly the kind of thing that looks
right in a mock and is wrong against the real service — unit tests alone weren't a high
enough bar for this particular piece. This test could not be run in this environment (no
Docker available in the sandbox this was built in) — it's syntax-checked and lint-clean, and
will get its first real execution in the project's own CI or local Docker Compose stack.

## 5. Definition of Done

- [x] `WeaviateStore.search()`/`.delete()` implemented against the verified real API.
- [x] `QdrantStore` fully implemented, using the non-deprecated `query_points()` endpoint.
- [x] `DualWriteVectorStore` implements the agreed failure policy (primary raises, secondary
      logs) with zero changes to `batch_worker.py`.
- [x] `get_store()` routes correctly for both `VECTOR_BACKEND` values.
- [x] Qdrant collection dimension is provider-aware (ADR-012's flagged gap resolved).
- [x] `QDRANT_PORT` default corrected everywhere it's declared.
- [x] Unit tests pass without real credentials or a live service (31 new tests).
- [x] A live-service integration test exists and is lint-clean; not executable in this build
      environment (no Docker available here) — first real run is in the project's own CI.

## 6. Carried-forward risks (not solved in this phase)

- **Qdrant drift**: repeated transient secondary-write failures for the same tenant leave
  Qdrant silently behind Weaviate — no reconciliation/backfill job exists. Worth a
  `pvh_qdrant_write_failures_total` counter + alert whenever Observability work happens.
- **Dense-only failover**: if Qdrant is ever promoted to primary via the manual DR runbook,
  retrieval loses the BM25/keyword half until Weaviate is restored — inherent to Qdrant's
  feature set, not a shortcut taken here.
- **The `src`-collision bug** (§3) — affects any future test file that needs both
  `ingestion` and `vector-store` (or any two services) on `sys.path` simultaneously.

## Footnotes (verified July 2026)

1. `weaviate-client` hybrid search's bring-your-own-vector pattern (`query=` text +
   `vector=` embedding together, `filters=` for pre-filtering) confirmed against current
   Weaviate documentation and multiple working code examples, not assumed from general
   familiarity with the API.
2. `qdrant-client` 1.18.0's `AsyncQdrantClient.search()`/`.search_batch()` deprecation in
   favor of `.query_points()` confirmed both via the GitHub project's own discussion thread
   and by introspecting the installed client's actual method signatures directly.
3. The `QDRANT_PORT` bug (§2) was confirmed by checking `AsyncQdrantClient.__init__`'s real
   signature (`port: int | None = 6333`, separate `grpc_port: int = 6334`), not assumed.
