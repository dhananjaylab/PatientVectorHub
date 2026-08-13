"""
WeaviateStore — implements VectorStoreInterface against the single
`PatientDocument` collection scripts/setup_weaviate_schema.py creates,
using Weaviate v4's native multi-tenancy (ADR-009).

upsert() and health_check() shipped in Phase 4 (ADR-011, pulled forward
from this phase). search() and delete() are Phase 6 (ADR-013): native
hybrid search (BM25 + bring-your-own-vector, since the collection has no
server-side vectorizer) and delete-by-filter. Verified against the
current weaviate-client v4 API: `collection.with_tenant(tenant)` returns
a tenant-scoped collection object without making a request; batch writes
go through `collection.data.insert_many([DataObject(...), ...])`; hybrid
search takes `query=` (BM25 text) and `vector=` (dense) together via
`collection.query.hybrid(...)`; deletes go through
`collection.data.delete_many(where=Filter...)`.

Phase 7 change: search() now runs the sync weaviate-client call via
`asyncio.to_thread()` instead of calling it directly inline. This file's
own Phase 6 docstring already flagged the reason: weaviate-client v4 has
no fully async surface, so calling it directly from `async def` blocks
the event loop for the call's full duration. That was an acceptable
trade for Phase 4's Celery-only write path and Phase 6's dual-write
addition (background workers, not interactively latency-sensitive), but
Phase 7 puts this exact code on the hot path of every `/v1/query` HTTP
request, where a blocked event loop stalls every other in-flight
request on the same worker process. upsert()/delete()/health_check()
are intentionally left as-is (still Celery/background-only call sites,
already tested across Phases 4 and 6) — narrowing the fix to the one
method that actually changed call sites, rather than touching
already-verified code for no behavioral reason.
"""

from __future__ import annotations

import asyncio
import uuid

import weaviate
from weaviate.classes.data import DataObject
from weaviate.classes.init import Auth
from weaviate.classes.query import Filter, MetadataQuery

from .config import settings
from .interface import Chunk, SearchResult, VectorStoreInterface

_COLLECTION_NAME = "PatientDocument"


def _chunk_uuid(doc_id: str, chunk_index: int) -> str:
    """Deterministic UUID per chunk -> idempotent upsert (re-processing
    the same document produces the same object IDs instead of
    duplicates)."""
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{doc_id}:{chunk_index}"))


def _connect() -> weaviate.WeaviateClient:
    if settings.WEAVIATE_URL:
        return weaviate.connect_to_weaviate_cloud(
            cluster_url=settings.WEAVIATE_URL,
            auth_credentials=(
                Auth.api_key(settings.WEAVIATE_API_KEY) if settings.WEAVIATE_API_KEY else None
            ),
        )
    return weaviate.connect_to_local(host=settings.WEAVIATE_HOST, port=settings.WEAVIATE_PORT)


class WeaviateStore(VectorStoreInterface):
    def __init__(self, tenant_id: str):
        self.tenant_id = tenant_id
        self._client = _connect()
        self._tenant_collection = self._client.collections.get(_COLLECTION_NAME).with_tenant(
            tenant_id
        )

    async def upsert(self, doc_id: str, chunks: list[Chunk], vectors: list[list[float]]) -> None:
        objects = [
            DataObject(
                properties={
                    "document_id": doc_id,
                    "chunk_text": chunks[i].text,
                    "document_type": chunks[i].metadata.get("document_type", ""),
                    "patient_id_hash": chunks[i].metadata.get("patient_id_hash", ""),
                    "model_version": settings.EMBEDDING_MODEL_VERSION,
                    "chunk_index": chunks[i].index,
                },
                vector=vectors[i],
                uuid=_chunk_uuid(doc_id, chunks[i].index),
            )
            for i in range(len(chunks))
        ]
        result = self._tenant_collection.data.insert_many(objects)
        if result.has_errors:
            raise RuntimeError(f"Weaviate upsert errors for doc {doc_id}: {result.errors}")

    async def health_check(self) -> bool:
        return self._client.is_ready()

    async def search(
        self,
        query: str,
        query_vector: list[float],
        top_k: int = 10,
        filters: dict | None = None,
    ) -> list[SearchResult]:
        """Native hybrid search (BM25 + vector, Reciprocal Rank Fusion by
        default). The collection uses self-provided vectors (ADR-009 — no
        server-side vectorizer), so `vector=` must be supplied explicitly
        for the dense half; `query=` still drives the BM25 half. See
        ADR-013 §1 for why the caller (not this module) computes
        query_vector.

        alpha=0.5 is Weaviate's own default (equal weight BM25/vector) —
        not tuned against PVH's actual corpus in this phase; revisit once
        Phase 7's RAG query engine has real queries to benchmark against.

        Runs the underlying sync client call via asyncio.to_thread() —
        see this module's docstring for why that changed in Phase 7.
        """
        wv_filter = _build_filter(filters)

        def _do_search():
            return self._tenant_collection.query.hybrid(
                query=query,
                vector=query_vector,
                alpha=0.5,
                limit=top_k,
                filters=wv_filter,
                return_metadata=MetadataQuery(score=True),
            )

        response = await asyncio.to_thread(_do_search)
        return [
            SearchResult(
                doc_id=o.properties["document_id"],
                chunk_text=o.properties["chunk_text"],
                score=o.metadata.score or 0.0,
                document_type=o.properties.get("document_type", ""),
                metadata=o.properties,
            )
            for o in response.objects
        ]

    async def delete(self, doc_id: str) -> None:
        self._tenant_collection.data.delete_many(
            where=Filter.by_property("document_id").equal(doc_id)
        )

    def close(self) -> None:
        self._client.close()


def _build_filter(filters: dict | None):
    """Translate the interface's plain-dict filters into a Weaviate
    Filter. Only document_types is used anywhere yet — extend here as
    real query needs show up rather than guessing at a fuller filter DSL
    now (unchanged reasoning from Phase 6; Phase 7 is the first caller
    but doesn't need more than this yet — see docs/adr/ADR-014 §2)."""
    if not filters:
        return None
    clauses = []
    if document_types := filters.get("document_types"):
        clauses.append(Filter.by_property("document_type").contains_any(document_types))
    if not clauses:
        return None
    if len(clauses) == 1:
        return clauses[0]
    combined = clauses[0]
    for clause in clauses[1:]:
        combined = combined & clause
    return combined
