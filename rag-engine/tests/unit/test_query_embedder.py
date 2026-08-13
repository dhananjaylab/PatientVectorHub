"""
Unit tests for rag-engine/src/query_embedder.py (Phase 7). Both providers'
network clients are mocked — no live OpenAI/HF endpoint needed to run this
file.
"""

import os

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

class TestProviderDispatch:
    @pytest.mark.asyncio
    async def test_openai_provider_calls_openai_path(self):
        from src import query_embedder
        from src.config import settings

        settings.EMBEDDING_PROVIDER = "openai"
        with patch.object(
            query_embedder,
            "_embed_query_openai",
            new=AsyncMock(return_value=[0.1, 0.2]),
        ) as mocked:
            result = await query_embedder.embed_query("diabetes management")
        mocked.assert_called_once_with("diabetes management")
        assert result == [0.1, 0.2]

    @pytest.mark.asyncio
    async def test_clinical_bert_provider_calls_hf_path(self):
        from src import query_embedder
        from src.config import settings

        settings.EMBEDDING_PROVIDER = "clinical_bert"
        with patch.object(
            query_embedder,
            "_embed_query_clinical_bert",
            new=AsyncMock(return_value=[0.3, 0.4]),
        ) as mocked:
            result = await query_embedder.embed_query("HbA1c elevated")
        mocked.assert_called_once_with("HbA1c elevated")
        assert result == [0.3, 0.4]
        settings.EMBEDDING_PROVIDER = "openai"  # reset for other tests

    @pytest.mark.asyncio
    async def test_unknown_provider_raises(self):
        from src import query_embedder
        from src.config import settings

        settings.EMBEDDING_PROVIDER = "not-a-real-provider"
        with pytest.raises(ValueError, match="Unknown EMBEDDING_PROVIDER"):
            await query_embedder.embed_query("text")
        settings.EMBEDDING_PROVIDER = "openai"  # reset for other tests

class TestOpenAIEmbedQuery:
    @pytest.mark.asyncio
    async def test_calls_embeddings_create_with_correct_args(self):
        from src import query_embedder
        from src.config import settings

        settings.EMBEDDING_MODEL_VERSION = "text-embedding-3-large"
        settings.EMBEDDING_DIMENSIONS = 1536

        fake_response = MagicMock()
        fake_response.data = [MagicMock(embedding=[0.1] * 1536)]
        fake_client = MagicMock()
        fake_client.embeddings.create = AsyncMock(return_value=fake_response)

        query_embedder._openai_client = None
        with patch.object(query_embedder, "_get_openai_client", return_value=fake_client):
            result = await query_embedder._embed_query_openai("clinical query text")

        assert len(result) == 1536
        _, kwargs = fake_client.embeddings.create.call_args
        assert kwargs["input"] == ["clinical query text"]
        assert kwargs["model"] == "text-embedding-3-large"
        assert kwargs["dimensions"] == 1536

    @pytest.mark.asyncio
    async def test_empty_api_key_does_not_crash_at_import(self):
        """Lazy-construction regression guard — matches the exact bug
        class ingestion/src/embeddings/openai_embedder.py's Phase 4 fix
        addressed: AsyncOpenAI(api_key="") raises OpenAIError at
        construction, which would crash on `import query_embedder` alone
        if the client were built eagerly at module scope."""
        from src import query_embedder
        from src.config import settings

        settings.OPENAI_API_KEY = ""
        query_embedder._openai_client = None
        client = query_embedder._get_openai_client()
        assert client is not None  # constructed with "not-configured", not empty string

class TestClinicalBertEmbedQuery:
    @pytest.mark.asyncio
    async def test_calls_feature_extraction_and_unwraps_single_result(self):
        from src import query_embedder

        fake_array = MagicMock()
        fake_array.tolist.return_value = [[0.5] * 768]
        fake_client = MagicMock()
        fake_client.feature_extraction = AsyncMock(return_value=fake_array)

        query_embedder._hf_client = None
        with patch.object(query_embedder, "_get_hf_client", return_value=fake_client):
            result = await query_embedder._embed_query_clinical_bert("query text")

        assert len(result) == 768
        _, kwargs = fake_client.feature_extraction.call_args
        assert kwargs.get("normalize") is True or fake_client.feature_extraction.call_args[0][
            0
        ] == ["query text"]

    def test_retryable_error_predicate_matches_timeout(self):
        from huggingface_hub.errors import InferenceTimeoutError
        from src.query_embedder import _is_retryable_hf_error

        assert _is_retryable_hf_error(InferenceTimeoutError("timed out")) is True

    def test_retryable_error_predicate_rejects_plain_exception(self):
        from src.query_embedder import _is_retryable_hf_error

        assert _is_retryable_hf_error(ValueError("not an HF error")) is False
