"""
Vector Store Layer integration test (ADR-013) — runs against real Weaviate
and Qdrant instances (the local Docker Compose stack, or the equivalent CI
services in .github/workflows/ci.yml), not mocks. Deliberately scoped to
`vector-store` only, not `ingestion` + `vector-store` together like
tests/integration/test_ingestion_end_to_end.py — see
docs/PHASE_6_IMPLEMENTATION_PLAN.md's note on the pre-existing `src`
package-name collision between services for why mixing them in one test
file's sys.path is currently unreliable. This file needs no real
embedder — a fixed, fake vector is enough to prove the storage layer
(upsert/search/delete, hybrid search wiring, dual-write fan-out) actually
works against the real services, independent of embedding-provider
correctness (already covered elsewhere: ADR-012's tests, and this
project's existing OpenAI-embedding end-to-end test).
"""

import os
import sys
import uuid
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration

TENANT_ID = "00000000-0000-0000-0000-000000000001"  # seeded by scripts/seed_data.py
FAKE_VECTOR_DIM = int(os.getenv("EMBEDDING_DIMENSIONS", "1536"))

def _fake_vector(seed: int) -> list[float]:
    """A deterministic, non-embedding vector — good enough to prove
    upsert/search round-trips correctly; not meant to have any semantic
    meaning."""
    return [((seed + i) % 97) / 97.0 for i in range(FAKE_VECTOR_DIM)]

@pytest.fixture
def chunk():
    from src.interface import Chunk

    return Chunk(
        text="Patient shows elevated HbA1c consistent with type 2 diabetes.",
        index=0,
        metadata={"document_type": "lab_result", "patient_id_hash": "hash-e2e"},
    )

class TestWeaviateStoreLive:
    @pytest.mark.asyncio
    async def test_upsert_then_search_finds_the_chunk(self, chunk):
        from src.weaviate_store import WeaviateStore

        store = WeaviateStore(TENANT_ID)
        doc_id = str(uuid.uuid4())
        vector = _fake_vector(seed=1)
        try:
            await store.upsert(doc_id, [chunk], [vector])
            results = await store.search("elevated HbA1c diabetes", vector, top_k=5)
            assert any(r.doc_id == doc_id for r in results)
        finally:
            await store.delete(doc_id)
            store.close()

    @pytest.mark.asyncio
    async def test_delete_removes_the_chunk(self, chunk):
        from src.weaviate_store import WeaviateStore

        store = WeaviateStore(TENANT_ID)
        doc_id = str(uuid.uuid4())
        vector = _fake_vector(seed=2)
        await store.upsert(doc_id, [chunk], [vector])

        await store.delete(doc_id)
        results = await store.search("elevated HbA1c diabetes", vector, top_k=20)

        assert not any(r.doc_id == doc_id for r in results)
        store.close()

    @pytest.mark.asyncio
    async def test_health_check_is_true_against_live_instance(self):
        from src.weaviate_store import WeaviateStore

        store = WeaviateStore(TENANT_ID)
        assert await store.health_check() is True
        store.close()

class TestQdrantStoreLive:
    @pytest.mark.asyncio
    async def test_upsert_then_search_finds_the_chunk(self, chunk):
        from src.qdrant_store import QdrantStore

        store = QdrantStore(TENANT_ID)
        doc_id = str(uuid.uuid4())
        vector = _fake_vector(seed=3)
        try:
            await store.upsert(doc_id, [chunk], [vector])
            results = await store.search("ignored", vector, top_k=5)
            assert any(r.doc_id == doc_id for r in results)
        finally:
            await store.delete(doc_id)
            await store.close()

    @pytest.mark.asyncio
    async def test_delete_removes_the_chunk(self, chunk):
        from src.qdrant_store import QdrantStore

        store = QdrantStore(TENANT_ID)
        doc_id = str(uuid.uuid4())
        vector = _fake_vector(seed=4)
        await store.upsert(doc_id, [chunk], [vector])

        await store.delete(doc_id)
        results = await store.search("ignored", vector, top_k=20)

        assert not any(r.doc_id == doc_id for r in results)
        await store.close()

    @pytest.mark.asyncio
    async def test_health_check_is_true_against_live_instance(self):
        from src.qdrant_store import QdrantStore

        store = QdrantStore(TENANT_ID)
        assert await store.health_check() is True
        await store.close()

class TestDualWriteLive:
    @pytest.mark.asyncio
    async def test_upsert_lands_in_both_real_backends(self, chunk):
        """The actual point of ADR-013's dual-write decision — proves it
        against real services, not just the mocked policy test in
        tests/unit/test_dual_write_store.py."""
        from src.dual_write_store import DualWriteVectorStore
        from src.qdrant_store import QdrantStore
        from src.weaviate_store import WeaviateStore

        weaviate_store = WeaviateStore(TENANT_ID)
        qdrant_store = QdrantStore(TENANT_ID)
        dual = DualWriteVectorStore(primary=weaviate_store, secondary=qdrant_store)

        doc_id = str(uuid.uuid4())
        vector = _fake_vector(seed=5)
        try:
            await dual.upsert(doc_id, [chunk], [vector])

            weaviate_results = await weaviate_store.search("HbA1c diabetes", vector, top_k=5)
            qdrant_results = await qdrant_store.search("ignored", vector, top_k=5)

            assert any(r.doc_id == doc_id for r in weaviate_results)
            assert any(r.doc_id == doc_id for r in qdrant_results)
        finally:
            await dual.delete(doc_id)
            await dual.close()
