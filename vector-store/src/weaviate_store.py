"""
Minimal WeaviateStore — Phase 4 scope only (ADR-011: pulled forward from
Phase 6, per your decision). Implements VectorStoreInterface.upsert() and
.health_check() using Weaviate v4's native multi-tenancy (ADR-009)
against the single `PatientDocument` collection
scripts/setup_weaviate_schema.py already creates.

search() and delete() are intentionally NotImplementedError until Phase
6/7 — ingestion doesn't need them, RAG query does. Verified against the
current weaviate-client v4 API: `collection.with_tenant(tenant)` returns
a tenant-scoped collection object without making a request; batch writes
go through `collection.data.insert_many([DataObject(...), ...])`.

Note: weaviate-client v4's sync API is called here from inside `async
def` methods (matching the original doc 27 reference pattern) — the v4
client does not offer a fully async surface for every operation, so this
briefly blocks the event loop per call. Acceptable for Phase 4's
ingestion-only write path; revisit if/when Phase 6/7 query latency makes
it worth wrapping in a thread executor.
"""
from __future__ import annotations

import uuid

import weaviate
from weaviate.classes.data import DataObject
from weaviate.classes.init import Auth

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
        self._tenant_collection = (
            self._client.collections.get(_COLLECTION_NAME).with_tenant(tenant_id)
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
        self, query: str, top_k: int = 10, filters: dict | None = None
    ) -> list[SearchResult]:
        raise NotImplementedError(
            "Hybrid search lands in Phase 6/7 — ingestion doesn't need it. "
            "See docs/PHASE_4_IMPLEMENTATION_PLAN.md §2/§11 (ADR-011)."
        )

    async def delete(self, doc_id: str) -> None:
        raise NotImplementedError(
            "Deferred to Phase 6 — see docs/PHASE_4_IMPLEMENTATION_PLAN.md §2/§11 (ADR-011)."
        )

    def close(self) -> None:
        self._client.close()
