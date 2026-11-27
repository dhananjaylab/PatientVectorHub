"""
Unit tests for vector-store/src/interface.py's get_store() factory
(ADR-013) — verifies VECTOR_BACKEND actually controls dual-write vs.
failover-mode routing.
"""

from unittest.mock import patch

from src.config import settings

class TestGetStore:
    def test_default_returns_dual_write_store(self):
        from src.dual_write_store import DualWriteVectorStore
        from src.interface import get_store

        with (
            patch.object(settings, "VECTOR_BACKEND", "weaviate"),
            patch("src.weaviate_store._connect"),
            patch("src.qdrant_store._connect"),
        ):
            store = get_store("tenant-a")

        assert isinstance(store, DualWriteVectorStore)

    def test_weaviate_backend_returns_dual_write_store(self):
        from src.dual_write_store import DualWriteVectorStore
        from src.interface import get_store

        with (
            patch.object(settings, "VECTOR_BACKEND", "weaviate"),
            patch("src.weaviate_store._connect"),
            patch("src.qdrant_store._connect"),
        ):
            store = get_store("tenant-a")

        assert isinstance(store, DualWriteVectorStore)

    def test_dual_write_store_wraps_weaviate_as_primary_and_qdrant_as_secondary(self):
        from src.interface import get_store
        from src.qdrant_store import QdrantStore
        from src.weaviate_store import WeaviateStore

        with (
            patch.object(settings, "VECTOR_BACKEND", "weaviate"),
            patch("src.weaviate_store._connect"),
            patch("src.qdrant_store._connect"),
        ):
            store = get_store("tenant-a")

        assert isinstance(store.primary, WeaviateStore)
        assert isinstance(store.secondary, QdrantStore)

    def test_qdrant_backend_returns_bare_qdrant_store_no_wrapper(self):
        """Failover mode (scripts/dr_switch_to_qdrant.sh) — writes should
        not keep trying to reach a presumably-down Weaviate."""
        from src.dual_write_store import DualWriteVectorStore
        from src.interface import get_store
        from src.qdrant_store import QdrantStore

        with patch.object(settings, "VECTOR_BACKEND", "qdrant"), patch(
            "src.qdrant_store._connect"
        ):
            store = get_store("tenant-a")

        assert isinstance(store, QdrantStore)
        assert not isinstance(store, DualWriteVectorStore)
