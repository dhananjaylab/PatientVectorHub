"""
QdrantStore — implements VectorStoreInterface against the per-tenant
`patient_docs_{tenant_id}` collections scripts/setup_qdrant_schema.py
creates (ADR-013). Dense-vector-only: Qdrant has no BM25/keyword-search
concept, so `search()`'s `query` text argument is accepted for interface
compatibility and otherwise ignored — only `query_vector` drives results.

Verified against the installed qdrant-client 1.18.0's actual method
signatures (not just docs): `.search()`/`.search_batch()` are deprecated
in favor of the universal `.query_points()` endpoint; `.upsert()`,
`.delete()`, and `.get_collections()` are unchanged. AsyncQdrantClient
mirrors QdrantClient's method set with `await` — used here rather than
the sync client, unlike WeaviateStore, since qdrant-client's async
surface is complete (no event-loop-blocking trade-off to accept).
"""

from __future__ import annotations

import uuid

from qdrant_client import AsyncQdrantClient
from qdrant_client.models import FieldCondition, Filter, MatchAny, MatchValue, PointStruct

from .config import settings
from .interface import Chunk, SearchResult, VectorStoreInterface


def _collection_name(tenant_id: str) -> str:
    """Matches scripts/setup_qdrant_schema.py's collection_name() exactly
    — the two must agree or upserts land in a collection search() (or the
    schema script's index creation) never looks at."""
    return f"patient_docs_{tenant_id.replace('-', '_')}"


def _point_id(doc_id: str, chunk_index: int) -> str:
    """Same deterministic-UUID scheme as weaviate_store.py's
    _chunk_uuid() — not the *same* UUID (different namespace tag), but
    the same idempotent-upsert property: re-processing a document
    produces the same point IDs instead of duplicates."""
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, f"qdrant:{doc_id}:{chunk_index}"))


def _connect() -> AsyncQdrantClient:
    if settings.QDRANT_URL:
        return AsyncQdrantClient(
            url=settings.QDRANT_URL,
            api_key=settings.QDRANT_API_KEY or None,
        )
    return AsyncQdrantClient(host=settings.QDRANT_HOST, port=settings.QDRANT_PORT)


class QdrantStore(VectorStoreInterface):
    def __init__(self, tenant_id: str):
        self.tenant_id = tenant_id
        self.collection_name = _collection_name(tenant_id)
        self._client = _connect()

    async def upsert(self, doc_id: str, chunks: list[Chunk], vectors: list[list[float]]) -> None:
        points = [
            PointStruct(
                id=_point_id(doc_id, chunks[i].index),
                vector=vectors[i],
                payload={
                    "document_id": doc_id,
                    "chunk_text": chunks[i].text,
                    "document_type": chunks[i].metadata.get("document_type", ""),
                    "patient_id_hash": chunks[i].metadata.get("patient_id_hash", ""),
                    "model_version": settings.EMBEDDING_MODEL_VERSION,
                    "chunk_index": chunks[i].index,
                },
            )
            for i in range(len(chunks))
        ]
        # wait=False: higher upsert throughput, background indexing —
        # acceptable here since Qdrant is the DR/secondary target, not
        # what search()/health_check() read from in normal operation
        # (see dual_write_store.py / ADR-013 §3).
        await self._client.upsert(collection_name=self.collection_name, points=points, wait=False)

    async def search(
        self, query: str, query_vector: list[float], top_k: int = 10, filters: dict | None = None
    ) -> list[SearchResult]:
        qdrant_filter = _build_filter(filters)
        response = await self._client.query_points(
            collection_name=self.collection_name,
            query=query_vector,
            query_filter=qdrant_filter,
            limit=top_k,
            with_payload=True,
        )
        return [
            SearchResult(
                doc_id=p.payload["document_id"],
                chunk_text=p.payload["chunk_text"],
                score=p.score,
                document_type=p.payload.get("document_type", ""),
                metadata=p.payload,
            )
            for p in response.points
        ]

    async def delete(self, doc_id: str) -> None:
        await self._client.delete(
            collection_name=self.collection_name,
            points_selector=Filter(
                must=[FieldCondition(key="document_id", match=MatchValue(value=doc_id))]
            ),
        )

    async def health_check(self) -> bool:
        try:
            await self._client.get_collections()
            return True
        except Exception:
            return False

    async def close(self) -> None:
        await self._client.close()


def _build_filter(filters: dict | None) -> Filter | None:
    """Same scope as weaviate_store.py's _build_filter() — only
    document_types is used anywhere yet (no caller exists before Phase
    7)."""
    if not filters:
        return None
    must = []
    if document_types := filters.get("document_types"):
        must.append(FieldCondition(key="document_type", match=MatchAny(any=document_types)))
    return Filter(must=must) if must else None
