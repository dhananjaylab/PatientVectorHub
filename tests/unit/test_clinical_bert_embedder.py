"""
Unit tests for ingestion/src/embeddings/clinical_bert_embedder.py (ADR-012)
— the Hugging Face InferenceClient is always mocked; no real HF_TOKEN, no
real network calls, no deployed endpoint needed to run this file.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "ingestion"))

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _fake_client(feature_extraction_mock):
    client = MagicMock()
    client.feature_extraction = feature_extraction_mock
    return client


class TestEmbedBatch:
    @pytest.mark.asyncio
    async def test_returns_vectors_in_input_order(self):
        from src.embeddings import clinical_bert_embedder

        fx_mock = AsyncMock(return_value=[[0.1] * 768, [0.2] * 768])
        with patch.object(
            clinical_bert_embedder, "_get_client", return_value=_fake_client(fx_mock)
        ):
            vectors = await clinical_bert_embedder.embed_batch(["chunk one", "chunk two"])

        assert len(vectors) == 2
        assert len(vectors[0]) == 768
        assert vectors[0][0] == 0.1 and vectors[1][0] == 0.2

    @pytest.mark.asyncio
    async def test_empty_input_returns_empty_list_without_calling_api(self):
        from src.embeddings import clinical_bert_embedder

        fx_mock = AsyncMock()
        with patch.object(
            clinical_bert_embedder, "_get_client", return_value=_fake_client(fx_mock)
        ):
            result = await clinical_bert_embedder.embed_batch([])

        assert result == []
        fx_mock.assert_not_called()

    @pytest.mark.asyncio
    async def test_sends_whole_batch_in_one_call_not_one_per_text(self):
        """TEI pools server-side and accepts a list input — one call per
        batch, not one call per text (see the module's _embed_one_batch
        docstring for why looping per-text would be both slower and,
        against a non-pooling backend, wrong)."""
        from src.embeddings import clinical_bert_embedder

        fx_mock = AsyncMock(return_value=[[0.1] * 768, [0.2] * 768, [0.3] * 768])
        with patch.object(
            clinical_bert_embedder, "_get_client", return_value=_fake_client(fx_mock)
        ):
            vectors = await clinical_bert_embedder.embed_batch(["a", "b", "c"])

        assert fx_mock.call_count == 1
        args, kwargs = fx_mock.call_args
        assert args[0] == ["a", "b", "c"]
        assert len(vectors) == 3

    @pytest.mark.asyncio
    async def test_normalize_param_is_passed_through(self):
        from src.embeddings import clinical_bert_embedder

        fx_mock = AsyncMock(return_value=[[0.1] * 768])
        with patch.object(
            clinical_bert_embedder, "_get_client", return_value=_fake_client(fx_mock)
        ):
            await clinical_bert_embedder.embed_batch(["one chunk"])

        _, kwargs = fx_mock.call_args
        assert kwargs["normalize"] is True

    @pytest.mark.asyncio
    async def test_batches_respect_embedding_batch_size(self):
        from src.config import settings
        from src.embeddings import clinical_bert_embedder

        original_batch_size = settings.EMBEDDING_BATCH_SIZE
        settings.EMBEDDING_BATCH_SIZE = 2
        try:
            fx_mock = AsyncMock(side_effect=[[[0.1] * 768, [0.2] * 768], [[0.3] * 768]])
            with patch.object(
                clinical_bert_embedder, "_get_client", return_value=_fake_client(fx_mock)
            ):
                vectors = await clinical_bert_embedder.embed_batch(["a", "b", "c"])

            assert fx_mock.call_count == 2
            assert len(vectors) == 3
        finally:
            settings.EMBEDDING_BATCH_SIZE = original_batch_size

    @pytest.mark.asyncio
    async def test_retries_on_inference_timeout_error(self):
        from huggingface_hub.errors import InferenceTimeoutError
        from src.embeddings import clinical_bert_embedder

        call_count = {"n": 0}

        async def flaky_feature_extraction(*args, **kwargs):
            call_count["n"] += 1
            if call_count["n"] < 2:
                raise InferenceTimeoutError("model unavailable")
            return [[0.1] * 768]

        with patch.object(
            clinical_bert_embedder,
            "_get_client",
            return_value=_fake_client(flaky_feature_extraction),
        ):
            vectors = await clinical_bert_embedder.embed_batch(["one chunk"])

        assert call_count["n"] == 2
        assert len(vectors) == 1

    def test_client_construction_is_lazy_not_at_import_time(self):
        """Regression-style guard, mirroring the exact bug class fixed for
        openai_embedder.py in Phase 4: a module-level client constructed
        eagerly would crash on `import clinical_bert_embedder` alone if
        HF_TOKEN / HF_EMBEDDING_ENDPOINT_URL aren't set — e.g. CI running
        with EMBEDDING_PROVIDER=openai, where this module is importable
        via the provider dispatcher but never actually used. Simply
        reaching this line (the module already imported at the top of
        this file) proves the import didn't raise."""
        from src.embeddings import clinical_bert_embedder

        assert hasattr(clinical_bert_embedder, "_get_client")

    def test_client_is_constructed_with_endpoint_url_and_token(self):
        from src.config import settings
        from src.embeddings import clinical_bert_embedder

        original_url = settings.HF_EMBEDDING_ENDPOINT_URL
        original_token = settings.HF_TOKEN
        clinical_bert_embedder._client = None  # force a fresh construction
        settings.HF_EMBEDDING_ENDPOINT_URL = "https://fake.endpoints.huggingface.cloud"
        settings.HF_TOKEN = "hf_fake_token"
        try:
            with patch("src.embeddings.clinical_bert_embedder.AsyncInferenceClient") as mock_cls:
                clinical_bert_embedder._get_client()
                mock_cls.assert_called_once_with(
                    model="https://fake.endpoints.huggingface.cloud",
                    token="hf_fake_token",
                )
        finally:
            settings.HF_EMBEDDING_ENDPOINT_URL = original_url
            settings.HF_TOKEN = original_token
            clinical_bert_embedder._client = None


class TestIsRetryableHfError:
    """_is_retryable_hf_error() drives the retry decorator's predicate —
    tested directly since constructing real HfHubHTTPError instances with
    genuine HTTP response objects (to hit the 4xx-vs-5xx branch) adds
    little over exercising the predicate function itself."""

    def test_inference_timeout_error_is_retryable(self):
        from huggingface_hub.errors import InferenceTimeoutError
        from src.embeddings.clinical_bert_embedder import _is_retryable_hf_error

        assert _is_retryable_hf_error(InferenceTimeoutError("timed out")) is True

    def test_http_5xx_is_retryable(self):
        from huggingface_hub.errors import HfHubHTTPError
        from src.embeddings.clinical_bert_embedder import _is_retryable_hf_error

        exc = MagicMock(spec=HfHubHTTPError)
        exc.response = MagicMock(status_code=503)
        assert _is_retryable_hf_error(exc) is True

    def test_http_429_is_retryable(self):
        from huggingface_hub.errors import HfHubHTTPError
        from src.embeddings.clinical_bert_embedder import _is_retryable_hf_error

        exc = MagicMock(spec=HfHubHTTPError)
        exc.response = MagicMock(status_code=429)
        assert _is_retryable_hf_error(exc) is True

    def test_http_401_is_not_retryable(self):
        from huggingface_hub.errors import HfHubHTTPError
        from src.embeddings.clinical_bert_embedder import _is_retryable_hf_error

        exc = MagicMock(spec=HfHubHTTPError)
        exc.response = MagicMock(status_code=401)
        assert _is_retryable_hf_error(exc) is False

    def test_unrelated_exception_is_not_retryable(self):
        from src.embeddings.clinical_bert_embedder import _is_retryable_hf_error

        assert _is_retryable_hf_error(ValueError("not an HF error")) is False
