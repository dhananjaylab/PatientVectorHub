"""
Unit tests for rag-engine/src/retriever.py (Phase 7) — the first real
caller of vector_store.interface.search() (ADR-013 §1). embed_query()
and get_store() are both mocked — no live embedding provider or vector
store needed to run this file.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "rag-engine"))

from unittest.mock import AsyncMock, patch

import pytest


class TestRetrieve:
    @pytest.mark.asyncio
    async def test_embeds_query_then_searches_store(self, mock_weaviate):
        from src import retriever

        with (
            patch.object(
                retriever, "embed_query", new=AsyncMock(return_value=[0.1, 0.2, 0.3])
            ) as mocked_embed,
            patch.object(retriever, "get_store", return_value=mock_weaviate) as mocked_get_store,
        ):
            results = await retriever.retrieve("tenant-a", "diabetes with elevated HbA1c", top_k=5)

        mocked_embed.assert_called_once_with("diabetes with elevated HbA1c")
        mocked_get_store.assert_called_once_with("tenant-a")
        mock_weaviate.search.assert_called_once_with(
            "diabetes with elevated HbA1c", [0.1, 0.2, 0.3], top_k=5, filters=None
        )
        assert len(results) == 2
        assert results[0].doc_id == "d-001"

    @pytest.mark.asyncio
    async def test_filters_passed_through_unchanged(self, mock_weaviate):
        from src import retriever

        filters = {"document_types": ["lab_result"]}
        with (
            patch.object(retriever, "embed_query", new=AsyncMock(return_value=[0.1])),
            patch.object(retriever, "get_store", return_value=mock_weaviate),
        ):
            await retriever.retrieve("tenant-a", "query", top_k=10, filters=filters)

        _, kwargs = mock_weaviate.search.call_args
        assert kwargs["filters"] == filters

    @pytest.mark.asyncio
    async def test_default_top_k_is_ten(self, mock_weaviate):
        from src import retriever

        with (
            patch.object(retriever, "embed_query", new=AsyncMock(return_value=[0.1])),
            patch.object(retriever, "get_store", return_value=mock_weaviate),
        ):
            await retriever.retrieve("tenant-a", "query")

        _, kwargs = mock_weaviate.search.call_args
        assert kwargs["top_k"] == 10
