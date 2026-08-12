"""
Unit tests for vector-store/src/weaviate_store.py's search() and delete()
(ADR-013). The weaviate-client is always mocked — no live Weaviate needed
to run this file. Live-service verification lives in
tests/integration/test_vector_store_layer.py instead.
"""

import os

from unittest.mock import MagicMock, patch

import pytest

def _make_store():
    """Construct a WeaviateStore with _connect() mocked out, so __init__
    doesn't try to open a real client connection."""
    from src.weaviate_store import WeaviateStore

    with patch("src.weaviate_store._connect") as mock_connect:
        mock_client = MagicMock()
        mock_collection = MagicMock()
        mock_client.collections.get.return_value = mock_collection
        mock_tenant_collection = MagicMock()
        mock_collection.with_tenant.return_value = mock_tenant_collection
        mock_connect.return_value = mock_client
        store = WeaviateStore("tenant-a")
    return store, mock_tenant_collection

class TestSearch:
    @pytest.mark.asyncio
    async def test_passes_query_text_and_vector_together(self):
        store, tenant_collection = _make_store()
        fake_object = MagicMock()
        fake_object.properties = {
            "document_id": "d-1",
            "chunk_text": "HbA1c 8.4%",
            "document_type": "lab_result",
        }
        fake_object.metadata.score = 0.87
        tenant_collection.query.hybrid.return_value = MagicMock(objects=[fake_object])

        results = await store.search("diabetes", [0.1, 0.2, 0.3], top_k=5)

        _, kwargs = tenant_collection.query.hybrid.call_args
        assert kwargs["query"] == "diabetes"
        assert kwargs["vector"] == [0.1, 0.2, 0.3]
        assert kwargs["limit"] == 5
        assert len(results) == 1
        assert results[0].doc_id == "d-1"
        assert results[0].score == 0.87

    @pytest.mark.asyncio
    async def test_no_filters_passes_none(self):
        store, tenant_collection = _make_store()
        tenant_collection.query.hybrid.return_value = MagicMock(objects=[])

        await store.search("query", [0.1], top_k=10, filters=None)

        _, kwargs = tenant_collection.query.hybrid.call_args
        assert kwargs["filters"] is None

    @pytest.mark.asyncio
    async def test_document_types_filter_is_translated(self):
        store, tenant_collection = _make_store()
        tenant_collection.query.hybrid.return_value = MagicMock(objects=[])

        await store.search(
            "query", [0.1], filters={"document_types": ["lab_result", "clinical_note"]}
        )

        _, kwargs = tenant_collection.query.hybrid.call_args
        assert kwargs["filters"] is not None

    @pytest.mark.asyncio
    async def test_missing_score_defaults_to_zero(self):
        store, tenant_collection = _make_store()
        fake_object = MagicMock()
        fake_object.properties = {"document_id": "d-1", "chunk_text": "x", "document_type": ""}
        fake_object.metadata.score = None
        tenant_collection.query.hybrid.return_value = MagicMock(objects=[fake_object])

        results = await store.search("q", [0.1])

        assert results[0].score == 0.0

class TestDelete:
    @pytest.mark.asyncio
    async def test_deletes_by_document_id_filter(self):
        store, tenant_collection = _make_store()

        await store.delete("doc-123")

        tenant_collection.data.delete_many.assert_called_once()
        _, kwargs = tenant_collection.data.delete_many.call_args
        assert "where" in kwargs
