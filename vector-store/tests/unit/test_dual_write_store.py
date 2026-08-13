"""
Unit tests for vector-store/src/dual_write_store.py's fan-out and failure
policy (ADR-013 §3). Both underlying stores are fakes here — this file
tests the *policy*, not either backend's own correctness (see
test_weaviate_search_delete.py / test_qdrant_store.py for that).
"""

from unittest.mock import AsyncMock, MagicMock

import pytest


def _fake_backend(name: str):
    backend = MagicMock(name=name)
    backend.upsert = AsyncMock(return_value=None)
    backend.search = AsyncMock(return_value=["result"])
    backend.delete = AsyncMock(return_value=None)
    backend.health_check = AsyncMock(return_value=True)
    return backend


class TestUpsert:
    @pytest.mark.asyncio
    async def test_writes_to_both_stores(self):
        from src.dual_write_store import DualWriteVectorStore

        primary, secondary = _fake_backend("primary"), _fake_backend("secondary")
        store = DualWriteVectorStore(primary=primary, secondary=secondary)

        await store.upsert("doc-1", ["chunk"], [[0.1]])

        primary.upsert.assert_awaited_once_with("doc-1", ["chunk"], [[0.1]])
        secondary.upsert.assert_awaited_once_with("doc-1", ["chunk"], [[0.1]])

    @pytest.mark.asyncio
    async def test_primary_failure_raises(self):
        """Preserves batch_worker.py's existing retry/DLQ behavior
        unchanged — a wrapper failure must look identical to a bare
        WeaviateStore failure from the caller's point of view."""
        from src.dual_write_store import DualWriteVectorStore

        primary, secondary = _fake_backend("primary"), _fake_backend("secondary")
        primary.upsert = AsyncMock(side_effect=RuntimeError("weaviate down"))
        store = DualWriteVectorStore(primary=primary, secondary=secondary)

        with pytest.raises(RuntimeError, match="weaviate down"):
            await store.upsert("doc-1", ["chunk"], [[0.1]])

        secondary.upsert.assert_not_awaited()  # never reached — primary raised first

    @pytest.mark.asyncio
    async def test_secondary_failure_is_swallowed_not_raised(self):
        """A DR copy running behind is a lesser problem than failing
        ingestion because the backup target had a bad moment (ADR-013)."""
        from src.dual_write_store import DualWriteVectorStore

        primary, secondary = _fake_backend("primary"), _fake_backend("secondary")
        secondary.upsert = AsyncMock(side_effect=RuntimeError("qdrant unreachable"))
        store = DualWriteVectorStore(primary=primary, secondary=secondary)

        await store.upsert("doc-1", ["chunk"], [[0.1]])  # must not raise

        primary.upsert.assert_awaited_once()


class TestDelete:
    @pytest.mark.asyncio
    async def test_deletes_from_both_stores(self):
        from src.dual_write_store import DualWriteVectorStore

        primary, secondary = _fake_backend("primary"), _fake_backend("secondary")
        store = DualWriteVectorStore(primary=primary, secondary=secondary)

        await store.delete("doc-1")

        primary.delete.assert_awaited_once_with("doc-1")
        secondary.delete.assert_awaited_once_with("doc-1")

    @pytest.mark.asyncio
    async def test_secondary_delete_failure_is_swallowed(self):
        from src.dual_write_store import DualWriteVectorStore

        primary, secondary = _fake_backend("primary"), _fake_backend("secondary")
        secondary.delete = AsyncMock(side_effect=RuntimeError("qdrant unreachable"))
        store = DualWriteVectorStore(primary=primary, secondary=secondary)

        await store.delete("doc-1")  # must not raise

    @pytest.mark.asyncio
    async def test_primary_delete_failure_raises(self):
        from src.dual_write_store import DualWriteVectorStore

        primary, secondary = _fake_backend("primary"), _fake_backend("secondary")
        primary.delete = AsyncMock(side_effect=RuntimeError("weaviate down"))
        store = DualWriteVectorStore(primary=primary, secondary=secondary)

        with pytest.raises(RuntimeError, match="weaviate down"):
            await store.delete("doc-1")


class TestSearchAndHealthCheck:
    @pytest.mark.asyncio
    async def test_search_reads_from_primary_only(self):
        from src.dual_write_store import DualWriteVectorStore

        primary, secondary = _fake_backend("primary"), _fake_backend("secondary")
        store = DualWriteVectorStore(primary=primary, secondary=secondary)

        results = await store.search("query text", [0.1], top_k=5)

        primary.search.assert_awaited_once_with("query text", [0.1], top_k=5, filters=None)
        secondary.search.assert_not_awaited()
        assert results == ["result"]

    @pytest.mark.asyncio
    async def test_health_check_reads_from_primary_only(self):
        from src.dual_write_store import DualWriteVectorStore

        primary, secondary = _fake_backend("primary"), _fake_backend("secondary")
        store = DualWriteVectorStore(primary=primary, secondary=secondary)

        assert await store.health_check() is True
        primary.health_check.assert_awaited_once()
        secondary.health_check.assert_not_awaited()


class TestClose:
    @pytest.mark.asyncio
    async def test_close_handles_sync_and_async_close_methods(self):
        """WeaviateStore.close() is sync; QdrantStore.close() is async —
        the wrapper must handle both without assuming either shape."""
        from src.dual_write_store import DualWriteVectorStore

        primary, secondary = _fake_backend("primary"), _fake_backend("secondary")
        primary.close = MagicMock()  # sync, like WeaviateStore
        secondary.close = AsyncMock()  # async, like QdrantStore
        store = DualWriteVectorStore(primary=primary, secondary=secondary)

        await store.close()

        primary.close.assert_called_once()
        secondary.close.assert_awaited_once()
