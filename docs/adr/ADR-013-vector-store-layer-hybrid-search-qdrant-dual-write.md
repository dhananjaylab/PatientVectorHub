# ADR-013: Vector Store Layer Completion — Hybrid Search, Qdrant Dual-Write, and the `query_vector` Interface Change

**Date:** 2026-07-26
**Status:** Accepted
**Relates to:** ADR-009 (native multi-tenancy, OpenAI embeddings), ADR-011 (minimal Weaviate
writes pulled into Phase 4), ADR-012 (clinical_bert provider + dimensions),
`vector-store/src/interface.py`, `weaviate_store.py`, `qdrant_store.py`, `dual_write_store.py`

## Context

ADR-011 pulled `WeaviateStore.upsert()` and `.health_check()` forward into Phase 4;
`.search()` and `.delete()` were left raising `NotImplementedError`, and `QdrantStore` didn't
exist at all. This phase completes that: real hybrid search, real delete, a real Qdrant
store, and — per the decision made at the start of this build — **dual-write to both
Weaviate and Qdrant on every ingestion upsert**, not a standalone/inactive Qdrant store.

Three sub-decisions fell out of finishing this for real rather than stubbing it further.

## Decision

### 1. `search()` gains a `query_vector` parameter — this is a real interface change

`VectorStoreInterface.search()` was `search(query: str, top_k, filters)`. Implementing it
for real surfaced a problem: our `PatientDocument` Weaviate collection uses
`Configure.Vectors.self_provided()` (ADR-009 — no server-side vectorizer), so Weaviate's
`.query.hybrid()` needs an explicit `vector=` for its dense half; passing only `query=` text
would only run the BM25 half. Qdrant has no BM25 concept at all — it's pure dense-vector
search and needs a query vector unconditionally.

Turning the query text into a vector requires an embedder, and the embedders live in
`ingestion/src/embeddings/` (ADR-009/012). Making `vector-store` import from `ingestion` to
embed queries would invert the dependency direction Phase 4 established (`ingestion` already
imports `vector_store` for storage; `vector_store` reaching back into `ingestion` to embed a
query string would make the two packages circularly dependent on each other).

Instead: `search()` is now `search(query: str, query_vector: list[float], top_k=10,
filters=None)`. The caller — whichever service is doing retrieval — embeds the query text
itself (using whichever embedder its own `EMBEDDING_PROVIDER` is configured for) and passes
both the raw text (for Weaviate's BM25 half) and the vector (for the dense half, and for
Qdrant's only half) into `search()`. `vector_store` stays a pure storage abstraction with no
embedding-provider dependency of its own. There is no caller of `search()` yet — Phase 7 (RAG
Query Engine) is the first one — so this is a clean signature change, not a breaking one.

### 2. `QdrantStore`: dense-only, `query_points()` not the deprecated `search()`

`qdrant-client`'s `.search()`/`.search_batch()` are deprecated in favor of the universal
`.query_points()` endpoint (confirmed via the installed `1.18.0` client's actual method
signatures, not just docs). `QdrantStore.search()` calls `query_points(collection_name=...,
query=query_vector, query_filter=..., limit=top_k, with_payload=True)` and reads
`.points[i].score` / `.payload`. No BM25/text component — `query` (the text arg) is accepted
for interface compatibility and ignored.

Collections are per-tenant (`patient_docs_{tenant_id}`, matching
`scripts/setup_qdrant_schema.py`'s existing naming), unlike Weaviate's single
natively-multi-tenant collection — Qdrant's multi-tenancy model favors this per-tenant-
collection pattern for the same effective isolation.

### 3. Dual-write, encapsulated in `get_store()` — zero changes to `batch_worker.py`

Per this session's decision, every ingestion upsert now writes to both stores. Rather than
teaching `batch_worker.py` to call two stores, `dual_write_store.py`'s
`DualWriteVectorStore` wraps a primary (Weaviate) and secondary (Qdrant) store behind the
same `VectorStoreInterface`. `get_store(tenant_id)` returns:

- `VECTOR_BACKEND=weaviate` (default): `DualWriteVectorStore(primary=WeaviateStore(...),
  secondary=QdrantStore(...))`.
- `VECTOR_BACKEND=qdrant` (manual DR failover, per `scripts/dr_switch_to_qdrant.sh`): a bare
  `QdrantStore(...)`, no wrapper. During an actual Weaviate outage, new writes shouldn't
  keep trying to reach the (presumably down) primary — this matches the existing runbook's
  intent of flipping the *active* backend, not writing to both while one is known-bad.

Failure policy inside the wrapper, since "every upsert writes to both" doesn't by itself say
what happens when one write fails:

- **Weaviate (primary) failure → raises.** This preserves Phase 4's already-tested
  retry/DLQ behavior in `batch_worker.py` exactly as-is — `process_document`'s `except`
  block doesn't know or care that a wrapper is involved.
- **Qdrant (secondary/DR) failure → logged, does not raise.** A DR copy that's temporarily
  behind is a lesser problem than failing (and retrying, and eventually DLQ-ing) a document
  because the *backup* target had a bad moment. This does mean Qdrant can drift out of sync
  with Weaviate on transient Qdrant errors — there's no reconciliation job in this phase;
  flagged below as a carried-forward risk, not solved here.

`search()`, `delete()`, and `health_check()` route to the *primary only* in the default
(dual-write) case — reads are not fanned out or automatically failed over. Read failover is
still the manual runbook (flip `VECTOR_BACKEND`, restart), unchanged from what
`scripts/dr_switch_to_qdrant.sh` already documented. `delete()` on the wrapper does fan out
to both stores (a delete that only removes from the primary and leaves the DR copy behind
would itself be a compliance gap for a "no raw PHI in the vector store" project), with the
same failure policy as upsert.

### 4. Qdrant collection dimension is now provider-aware

`scripts/setup_qdrant_schema.py` was hardcoded to `EMBEDDING_DIMENSIONS` (the OpenAI-path
setting). ADR-012 flagged but didn't fix this gap. It now reads whichever dimension matches
the *active* `EMBEDDING_PROVIDER` — `EMBEDDING_DIMENSIONS` (1536) for `openai`,
`CLINICAL_BERT_DIMENSIONS` (768) for `clinical_bert` — via a new field added to
`vector-store/src/config.py`. Weaviate doesn't need the equivalent treatment: self-provided-
vector collections don't declare a fixed size at schema-creation time the way Qdrant's
`VectorParams(size=...)` does.

### 5. `QDRANT_PORT` default was wrong everywhere — fixed as part of this phase

Every service's config (`vector-store`, `ingestion`, `api-gateway`, `rag-engine`) and
`.env.example` defaulted `QDRANT_PORT` to `6334` — Qdrant's **gRPC** port. `AsyncQdrantClient`'s
`port=` kwarg expects the **REST** port, `6333` (gRPC is a separate `grpc_port` kwarg, unused
here — nothing in this codebase sets `prefer_grpc=True`). This was latent and harmless before
this phase: `QdrantStore` didn't exist, so nothing ever actually opened a connection with the
wrong port. Building the first real Qdrant connection is what surfaced it. Fixed to `6333`
everywhere the value is declared; `docker-compose.yml` already exposes both ports, so no
infra change was needed, only the client-facing default.

## Consequences

- No changes to `batch_worker.py`, `ingest.py`, or any Phase 4 code that calls `get_store()`
  — the dual-write policy is entirely inside `get_store()`'s returned object.
- New risk, carried forward rather than solved: Qdrant can silently drift behind Weaviate if
  a transient Qdrant write error is logged-and-swallowed repeatedly for the same tenant.
  There's no reconciliation/backfill job in this phase. Worth a `pvh_qdrant_write_failures_total`
  Prometheus counter and an alert when Phase 8/Observability work happens — not built here.
- `search()`'s new `query_vector` parameter means any future caller must embed the query
  itself before calling — this is a real API contract, not just a convenience default, and
  should be documented for whoever builds Phase 7.
- `QdrantStore.search()` returns no BM25/keyword signal at all — if Qdrant is ever promoted
  to *primary* during a real failover, retrieval quality changes (dense-only vs. hybrid)
  until Weaviate is restored. This is inherent to Qdrant's feature set, not a shortcut taken
  here.
- Integration tests now exercise real Weaviate hybrid search and a real Qdrant instance in
  CI (new `qdrant:` service, mirroring the existing `weaviate:` one) — this is a meaningfully
  higher bar than Phase 4/5's unit-mock-only posture, justified because API-shape correctness
  (hybrid `vector=`/`query=` combination, `query_points()` vs. deprecated `search()`) is
  exactly the kind of thing that looks right in a mock and is wrong against the real service.

## References

- `docs/adr/ADR-009-aiven-openai-native-multitenancy-pivot.md`
- `docs/PHASE_4_IMPLEMENTATION_PLAN.md` (§2, §11 — ADR-011's original deferral)
- `docs/adr/ADR-012-hf-hosted-clinical-bert-embedding-server.md` (§6 — the dimension gap
  this ADR resolves)
- `docs/PHASE_6_IMPLEMENTATION_PLAN.md`
- Weaviate hybrid search (BYOV — `query=` + `vector=` together):
  https://docs.weaviate.io/weaviate/search/hybrid
- Weaviate delete-by-filter: https://docs.weaviate.io/weaviate/manage-objects/delete
- Qdrant `query_points()` as the universal search endpoint (supersedes deprecated
  `search()`/`search_batch()`): https://github.com/qdrant/qdrant-client
