"""
VectorStoreInterface — ABC for Weaviate and Qdrant implementations.

Phase 4 update: get_store() now actually returns a working WeaviateStore
(see weaviate_store.py, ADR-011) instead of unconditionally raising
NotImplementedError. QdrantStore stays unimplemented — the DR failover
path is explicitly Phase 6+ scope.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class Chunk:
    """A single text chunk with position and metadata."""
    text:     str
    index:    int
    metadata: dict = field(default_factory=dict)


@dataclass
class SearchResult:
    """A single vector search result."""
    doc_id:        str
    chunk_text:    str
    score:         float
    document_type: str
    metadata:      dict = field(default_factory=dict)


class VectorStoreInterface(ABC):
    """Abstract base class all vector store backends must implement."""

    @abstractmethod
    async def upsert(self, doc_id: str, chunks: list[Chunk], vectors: list[list[float]]) -> None:
        """Upsert chunk embeddings into the vector store."""
        ...

    @abstractmethod
    async def search(
        self, query: str, top_k: int = 10, filters: dict | None = None
    ) -> list[SearchResult]:
        """Hybrid search — returns top_k most relevant chunks."""
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
    Phase 4 (ADR-011): WeaviateStore is real. QdrantStore (DR path)
    remains Phase 6+.
    """
    import os
    backend = os.getenv("VECTOR_BACKEND", "weaviate")
    if backend == "qdrant":
        raise NotImplementedError("QdrantStore (DR path) lands in Phase 6")
    from .weaviate_store import WeaviateStore
    return WeaviateStore(tenant_id)
