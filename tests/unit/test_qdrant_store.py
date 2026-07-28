"""
Unit tests for vector-store/src/qdrant_store.py (ADR-013). AsyncQdrantClient
is always mocked — no live Qdrant needed to run this file. Live-service
verification lives in tests/integration/test_vector_store_layer.py.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "vector-store"))

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _make_store():
    from src.qdrant_store import QdrantStore

    with patch("src.qdrant_store._connect") as mock_connect:
        mock_client = AsyncMock()
        mock_connect.return_value = mock_client
        store = QdrantStore("11111111-1111-1111-1111-111111111111")
    return store, mock_client


class TestCollectionNaming:
    def test_collection_name_matches_setup_script_convention(self):
        from src.qdrant_store import _collection_name

        assert _collection_name("11111111-1111-1111-1111-111111111111") == (
            "patient_docs_11111111_1111_1111_1111_111111111111"
        )


class TestUpsert:
    @pytest.mark.asyncio
    async def test_upsert_sends_points_with_payload(self):
        from src.interface import Chunk

        store, client = _make_store()
        chunks = [Chunk(text="chunk one", index=0, metadata={"document_type": "lab_result"})]

        await store.upsert("doc-1", chunks, [[0.1, 0.2]])

        client.upsert.assert_awaited_once()
        _, kwargs = client.upsert.call_args
        assert kwargs["collection_name"] == store.collection_name
        assert len(kwargs["points"]) == 1
        assert kwargs["points"][0].vector == [0.1, 0.2]
        assert kwargs["points"][0].payload["document_id"] == "doc-1"
        assert kwargs["wait"] is False

    @pytest.mark.asyncio
    async def test_upsert_point_ids_are_deterministic(self):
        from src.interface import Chunk

        store, client = _make_store()
        chunks = [Chunk(text="x", index=0, metadata={})]

        await store.upsert("doc-1", chunks, [[0.1]])
        first_call_id = client.upsert.call_args.kwargs["points"][0].id

        await store.upsert("doc-1", chunks, [[0.1]])
        second_call_id = client.upsert.call_args.kwargs["points"][0].id

        assert first_call_id == second_call_id  # idempotent re-processing


class TestSearch:
    @pytest.mark.asyncio
    async def test_search_uses_query_points_not_deprecated_search(self):
        store, client = _make_store()
        fake_point = MagicMock()
        fake_point.payload = {
            "document_id": "d-1",
            "chunk_text": "text",
            "document_type": "lab_result",
        }
        fake_point.score = 0.9
        client.query_points = AsyncMock(return_value=MagicMock(points=[fake_point]))

        results = await store.search("ignored text", [0.1, 0.2], top_k=3)

        client.query_points.assert_awaited_once()
        _, kwargs = client.query_points.call_args
        assert kwargs["query"] == [0.1, 0.2]
        assert kwargs["limit"] == 3
        assert len(results) == 1
        assert results[0].doc_id == "d-1"
        assert results[0].score == 0.9
        # search() must never call the deprecated .search()/.search_batch()
        assert not hasattr(client, "search") or not client.search.called

    @pytest.mark.asyncio
    async def test_document_types_filter_becomes_field_condition(self):
        store, client = _make_store()
        client.query_points = AsyncMock(return_value=MagicMock(points=[]))

        await store.search("q", [0.1], filters={"document_types": ["lab_result"]})

        _, kwargs = client.query_points.call_args
        assert kwargs["query_filter"] is not None

    @pytest.mark.asyncio
    async def test_no_filters_passes_none(self):
        store, client = _make_store()
        client.query_points = AsyncMock(return_value=MagicMock(points=[]))

        await store.search("q", [0.1], filters=None)

        _, kwargs = client.query_points.call_args
        assert kwargs["query_filter"] is None


class TestDelete:
    @pytest.mark.asyncio
    async def test_deletes_by_document_id_match_value(self):
        store, client = _make_store()

        await store.delete("doc-123")

        client.delete.assert_awaited_once()
        _, kwargs = client.delete.call_args
        assert kwargs["collection_name"] == store.collection_name
        assert "points_selector" in kwargs


class TestHealthCheck:
    @pytest.mark.asyncio
    async def test_healthy_when_get_collections_succeeds(self):
        store, client = _make_store()
        client.get_collections = AsyncMock(return_value=MagicMock())

        assert await store.health_check() is True

    @pytest.mark.asyncio
    async def test_unhealthy_when_get_collections_raises(self):
        store, client = _make_store()
        client.get_collections = AsyncMock(side_effect=ConnectionError("unreachable"))

        assert await store.health_check() is False
