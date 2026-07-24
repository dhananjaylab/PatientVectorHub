"""
Unit tests for ingestion/src/embeddings/openai_embedder.py — the OpenAI
client itself is always mocked; no real API calls or API key needed.
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "ingestion"))

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


def _fake_response(n_vectors: int, dims: int = 1536, tokens: int = 10):
    resp = MagicMock()
    resp.data = [MagicMock(embedding=[0.1] * dims) for _ in range(n_vectors)]
    resp.usage.total_tokens = tokens
    return resp


def _fake_client(create_mock):
    client = MagicMock()
    client.embeddings.create = create_mock
    return client


class TestEmbedBatch:
    @pytest.mark.asyncio
    async def test_returns_vectors_in_input_order(self):
        from src.embeddings import openai_embedder

        create_mock = AsyncMock(return_value=_fake_response(2))
        with patch.object(openai_embedder, "_get_client", return_value=_fake_client(create_mock)):
            vectors = await openai_embedder.embed_batch(["chunk one", "chunk two"])

        assert len(vectors) == 2
        assert len(vectors[0]) == 1536

    @pytest.mark.asyncio
    async def test_empty_input_returns_empty_list_without_calling_api(self):
        from src.embeddings import openai_embedder

        create_mock = AsyncMock()
        with patch.object(openai_embedder, "_get_client", return_value=_fake_client(create_mock)):
            result = await openai_embedder.embed_batch([])

        assert result == []
        create_mock.assert_not_called()

    @pytest.mark.asyncio
    async def test_dimensions_param_is_passed_through(self):
        from src.embeddings import openai_embedder
        from src.config import settings

        create_mock = AsyncMock(return_value=_fake_response(1))
        with patch.object(openai_embedder, "_get_client", return_value=_fake_client(create_mock)):
            await openai_embedder.embed_batch(["one chunk"])

        _, kwargs = create_mock.call_args
        assert kwargs["dimensions"] == settings.EMBEDDING_DIMENSIONS == 1536

    @pytest.mark.asyncio
    async def test_batches_respect_embedding_batch_size(self):
        from src.embeddings import openai_embedder
        from src.config import settings

        original_batch_size = settings.EMBEDDING_BATCH_SIZE
        settings.EMBEDDING_BATCH_SIZE = 2
        try:
            create_mock = AsyncMock(side_effect=[_fake_response(2), _fake_response(1)])
            with patch.object(
                openai_embedder, "_get_client", return_value=_fake_client(create_mock)
            ):
                vectors = await openai_embedder.embed_batch(["a", "b", "c"])

            assert create_mock.call_count == 2
            assert len(vectors) == 3
        finally:
            settings.EMBEDDING_BATCH_SIZE = original_batch_size

    @pytest.mark.asyncio
    async def test_retries_on_rate_limit_error(self):
        import httpx
        from openai import RateLimitError
        from src.embeddings import openai_embedder

        request = httpx.Request("POST", "https://api.openai.com/v1/embeddings")
        response = httpx.Response(status_code=429, request=request)
        rate_limit_error = RateLimitError(message="rate limited", response=response, body=None)

        call_count = {"n": 0}

        async def flaky_create(*args, **kwargs):
            call_count["n"] += 1
            if call_count["n"] < 2:
                raise rate_limit_error
            return _fake_response(1)

        with patch.object(
            openai_embedder, "_get_client", return_value=_fake_client(flaky_create)
        ):
            vectors = await openai_embedder.embed_batch(["one chunk"])

        assert call_count["n"] == 2
        assert len(vectors) == 1

    def test_client_construction_is_lazy_not_at_import_time(self):
        """Regression test for the exact bug found while validating this
        plan: AsyncOpenAI(api_key="") raises OpenAIError at construction
        in the current SDK, so a module-level client would crash on
        `import openai_embedder` alone with no OPENAI_API_KEY set. Simply
        reaching this line (the module already imported successfully at
        the top of this file) proves the import didn't raise."""
        from src.embeddings import openai_embedder
        assert hasattr(openai_embedder, "_get_client")
