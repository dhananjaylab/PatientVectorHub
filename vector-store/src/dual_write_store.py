"""
DualWriteVectorStore — wraps a primary (Weaviate) and secondary (Qdrant)
VectorStoreInterface so every upsert()/delete() reaches both backends,
per this session's decision (ADR-013 §3). Nothing outside
vector-store/src/interface.py's get_store() factory should construct
this directly.

Failure policy (see ADR-013 for the reasoning, not repeated here):
  - primary (Weaviate) failure -> raises, unchanged from pre-Phase-6
    behavior, so batch_worker.py's existing retry/DLQ logic keeps working
    exactly as already tested.
  - secondary (Qdrant) failure -> logged, swallowed. A DR copy running
    behind is a lesser problem than failing ingestion over a backup
    target having a bad moment. This does mean Qdrant can drift out of
    sync on repeated transient failures for the same tenant — there is
    no reconciliation job in this phase (see ADR-013 Consequences).

search() and health_check() read from the primary only — this wrapper
does not implement automatic read failover; that stays the manual
scripts/dr_switch_to_qdrant.sh runbook (flip VECTOR_BACKEND, restart).
"""

import logging

from .interface import Chunk, SearchResult, VectorStoreInterface

log = logging.getLogger(__name__)


class DualWriteVectorStore(VectorStoreInterface):
    def __init__(self, primary: VectorStoreInterface, secondary: VectorStoreInterface):
        self.primary = primary
        self.secondary = secondary

    async def upsert(self, doc_id: str, chunks: list[Chunk], vectors: list[list[float]]) -> None:
        await self.primary.upsert(doc_id, chunks, vectors)
        try:
            await self.secondary.upsert(doc_id, chunks, vectors)
        except Exception as exc:
            log.warning(
                "Secondary (DR) upsert failed for doc_id=%s — primary succeeded, "
                "continuing without failing the task. Qdrant is now behind for "
                "this document: %s",
                doc_id,
                exc,
            )

    async def search(
        self, query: str, query_vector: list[float], top_k: int = 10, filters: dict | None = None
    ) -> list[SearchResult]:
        return await self.primary.search(query, query_vector, top_k=top_k, filters=filters)

    async def delete(self, doc_id: str) -> None:
        await self.primary.delete(doc_id)
        try:
            await self.secondary.delete(doc_id)
        except Exception as exc:
            log.warning(
                "Secondary (DR) delete failed for doc_id=%s — primary succeeded, "
                "continuing. Qdrant retains a stale copy of this document: %s",
                doc_id,
                exc,
            )

    async def health_check(self) -> bool:
        return await self.primary.health_check()

    async def close(self) -> None:
        """Best-effort close of both underlying clients. Not currently
        called anywhere (batch_worker.py doesn't call close() on the
        Phase 4 WeaviateStore either — a pre-existing gap, not introduced
        here), but provided for whenever that's addressed. WeaviateStore's
        close() is sync (weaviate-client v4) and QdrantStore's is async
        (qdrant-client's AsyncQdrantClient) — this handles both rather
        than assuming either shape."""
        import inspect

        for store in (self.primary, self.secondary):
            close = getattr(store, "close", None)
            if not callable(close):
                continue
            result = close()
            if inspect.isawaitable(result):
                await result
