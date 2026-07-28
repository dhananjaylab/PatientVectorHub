"""
VectorStoreInterface — ABC for Weaviate and Qdrant implementations.

Phase 4 (ADR-011): get_store() returns a working WeaviateStore instead of
unconditionally raising NotImplementedError.

Phase 6 (ADR-013): search()/delete() are real (see weaviate_store.py),
QdrantStore exists (qdrant_store.py), and get_store() now returns a
DualWriteVectorStore that fans upsert()/delete() out to both backends —
see dual_write_store.py and ADR-013 for the failure-handling policy.
search() gained a required query_vector parameter: Weaviate's collection
uses self-provided vectors (no server-side vectorizer) and Qdrant has no
BM25 concept at all, so both backends need a precomputed query embedding,
not just the raw query text. Embedding the query is the caller's
responsibility (see ADR-013 §1 for why vector_store doesn't import
ingestion's embedders to do this itself).
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class Chunk:
    """A single text chunk with position and metadata."""

    text: str
    index: int
    metadata: dict = field(default_factory=dict)


@dataclass
class SearchResult:
    """A single vector search result."""

    doc_id: str
    chunk_text: str
    score: float
    document_type: str
    metadata: dict = field(default_factory=dict)


class VectorStoreInterface(ABC):
    """Abstract base class all vector store backends must implement."""

    @abstractmethod
    async def upsert(self, doc_id: str, chunks: list[Chunk], vectors: list[list[float]]) -> None:
        """Upsert chunk embeddings into the vector store."""
        ...

    @abstractmethod
    async def search(
        self, query: str, query_vector: list[float], top_k: int = 10, filters: dict | None = None
    ) -> list[SearchResult]:
        """Search for the top_k most relevant chunks.

        `query` is the raw query text — used for Weaviate's BM25 half of
        hybrid search; ignored by backends with no keyword-search concept
        (Qdrant). `query_vector` is the caller-computed embedding of that
        same text and is required by every backend (see ADR-013 §1)."""
        ...

    @abstractmethod
    async def delete(self, doc_id: str) -> None:
        """Delete all chunks for a document."""
        ...

    @abstractmethod
    async def health_check(self) -> bool:
        """Return True if the store is reachable and healthy."""
        ...


def get_store(tenant_id: str) -> VectorStoreInterface:
    """
    Factory — returns the correct backend based on VECTOR_BACKEND.

    "weaviate" (default): a DualWriteVectorStore wrapping WeaviateStore
    (primary — serves search()/delete()/health_check()) and QdrantStore
    (secondary — receives every upsert()/delete() too, per ADR-013's
    dual-write decision; write failures there are logged, not raised).

    "qdrant": a bare QdrantStore, no wrapper — manual DR failover mode
    (scripts/dr_switch_to_qdrant.sh), on the assumption Weaviate is the
    one that's down and shouldn't keep receiving writes.
    """
    import os

    backend = os.getenv("VECTOR_BACKEND", "weaviate")
    if backend == "qdrant":
        from .qdrant_store import QdrantStore

        return QdrantStore(tenant_id)
    from .dual_write_store import DualWriteVectorStore
    from .qdrant_store import QdrantStore
    from .weaviate_store import WeaviateStore

    return DualWriteVectorStore(primary=WeaviateStore(tenant_id), secondary=QdrantStore(tenant_id))
