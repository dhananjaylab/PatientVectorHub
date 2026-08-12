"""
Unit tests for ingestion/src/embeddings/__init__.py's provider dispatch
(ADR-012) — verifies EMBEDDING_PROVIDER actually controls which embedder
runs, since before this ADR it was a config field nothing read.
"""

import os

from unittest.mock import AsyncMock, patch

import pytest

@pytest.fixture(autouse=True)
def _restore_provider():
    from src.config import settings

    original = settings.EMBEDDING_PROVIDER
    yield
    settings.EMBEDDING_PROVIDER = original

class TestEmbeddingProviderDispatch:
    @pytest.mark.asyncio
    async def test_openai_provider_routes_to_openai_embedder(self):
        import src.embeddings as embeddings_pkg
        from src.config import settings

        settings.EMBEDDING_PROVIDER = "openai"
        with patch(
            "src.embeddings.openai_embedder.embed_batch",
            new_callable=AsyncMock,
            return_value=[[0.1] * 1536],
        ) as mock_openai:
            result = await embeddings_pkg.embed_batch(["text"])

        mock_openai.assert_awaited_once_with(["text"])
        assert result == [[0.1] * 1536]

    @pytest.mark.asyncio
    async def test_clinical_bert_provider_routes_to_clinical_bert_embedder(self):
        import src.embeddings as embeddings_pkg
        from src.config import settings

        settings.EMBEDDING_PROVIDER = "clinical_bert"
        with patch(
            "src.embeddings.clinical_bert_embedder.embed_batch",
            new_callable=AsyncMock,
            return_value=[[0.2] * 768],
        ) as mock_cb:
            result = await embeddings_pkg.embed_batch(["text"])

        mock_cb.assert_awaited_once_with(["text"])
        assert result == [[0.2] * 768]

    @pytest.mark.asyncio
    async def test_unknown_provider_raises_value_error(self):
        import src.embeddings as embeddings_pkg
        from src.config import settings

        settings.EMBEDDING_PROVIDER = "not-a-real-provider"
        with pytest.raises(ValueError, match="Unknown EMBEDDING_PROVIDER"):
            await embeddings_pkg.embed_batch(["text"])

    @pytest.mark.asyncio
    async def test_default_provider_is_openai(self):
        """Guards ADR-012's explicit statement that this ADR does not flip
        the default — only Settings() field defaults determine this, not
        any override a prior test left behind (the _restore_provider
        fixture resets EMBEDDING_PROVIDER, but this test asserts the
        actual shipped default independent of that reset)."""
        from src.config import Settings

        assert Settings.model_fields["EMBEDDING_PROVIDER"].default == "openai"
