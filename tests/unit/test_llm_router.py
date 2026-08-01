"""
Unit tests for rag-engine/src/llm_router.py (Phase 7). All three provider
SDKs are mocked — no live Anthropic/OpenAI/Gemini call needed to run this
file.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "rag-engine"))

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestProviderDispatch:
    @pytest.mark.asyncio
    async def test_default_provider_is_anthropic(self):
        from src.config import settings
        from src.llm_router import LLMRouter

        assert settings.LLM_DEFAULT_PROVIDER == "anthropic"
        router = LLMRouter()
        with patch(
            "src.llm_router._complete_anthropic", new=AsyncMock(return_value="answer")
        ) as mocked:
            result = await router.complete("prompt text")
        mocked.assert_called_once()
        assert result == "answer"

    @pytest.mark.asyncio
    async def test_explicit_provider_overrides_default(self):
        from src.llm_router import LLMRouter

        router = LLMRouter()
        with patch(
            "src.llm_router._complete_openai",
            new=AsyncMock(return_value="openai answer"),
        ) as mocked:
            result = await router.complete("prompt", provider="openai")
        mocked.assert_called_once()
        assert result == "openai answer"

    @pytest.mark.asyncio
    async def test_unknown_provider_raises(self):
        from src.llm_router import LLMRouter

        router = LLMRouter()
        with pytest.raises(ValueError, match="Unknown llm_provider"):
            await router.complete("prompt", provider="not-a-real-provider")

    @pytest.mark.asyncio
    async def test_max_tokens_defaults_to_settings_value(self):
        from src.config import settings
        from src.llm_router import LLMRouter

        router = LLMRouter()
        with patch("src.llm_router._complete_anthropic", new=AsyncMock(return_value="x")) as mocked:
            await router.complete("prompt")
        mocked.assert_called_once_with("prompt", settings.LLM_MAX_TOKENS)


class TestAnthropicProvider:
    @pytest.mark.asyncio
    async def test_extracts_text_from_content_block(self):
        from src import llm_router

        fake_message = MagicMock()
        fake_message.content = [MagicMock(text="the synthesized answer")]
        fake_client = MagicMock()
        fake_client.messages.create = AsyncMock(return_value=fake_message)

        llm_router._anthropic_client = None
        with patch.object(llm_router, "_get_anthropic_client", return_value=fake_client):
            result = await llm_router._complete_anthropic("prompt", 500)

        assert result == "the synthesized answer"
        _, kwargs = fake_client.messages.create.call_args
        assert kwargs["max_tokens"] == 500
        assert kwargs["messages"] == [{"role": "user", "content": "prompt"}]

    def test_empty_api_key_client_still_constructs(self):
        """anthropic 0.120.2's AsyncAnthropic(api_key="") does not raise
        at construction (verified against the installed SDK — unlike
        openai's client) — confirms the lazy `or "not-configured"` guard
        doesn't mask a construction-time crash that isn't actually there
        for this provider, while still being harmless to keep for
        consistency across all three providers in this file."""
        from src import llm_router
        from src.config import settings

        settings.ANTHROPIC_API_KEY = ""
        llm_router._anthropic_client = None
        client = llm_router._get_anthropic_client()
        assert client is not None


class TestOpenAIProvider:
    @pytest.mark.asyncio
    async def test_extracts_content_from_choices(self):
        from src import llm_router

        fake_response = MagicMock()
        fake_response.choices = [MagicMock(message=MagicMock(content="openai's answer"))]
        fake_client = MagicMock()
        fake_client.chat.completions.create = AsyncMock(return_value=fake_response)

        llm_router._openai_llm_client = None
        with patch.object(llm_router, "_get_openai_llm_client", return_value=fake_client):
            result = await llm_router._complete_openai("prompt", 500)

        assert result == "openai's answer"

    def test_empty_api_key_client_construction_is_deferred(self):
        """openai 2.50.0's AsyncOpenAI(api_key="") DOES raise at
        construction (verified against the installed SDK) — this is
        exactly why _get_openai_llm_client() passes "not-configured"
        instead of the empty string, same fix as
        ingestion/src/embeddings/openai_embedder.py's _get_client()."""
        from src import llm_router
        from src.config import settings

        settings.OPENAI_API_KEY = ""
        llm_router._openai_llm_client = None
        client = llm_router._get_openai_llm_client()  # must NOT raise
        assert client is not None

    @pytest.mark.asyncio
    async def test_none_content_raises_instead_of_returning_none(self):
        """openai's SDK types message.content as `str | None` — a
        tool-call-only response (not expected for this plain-text
        completion, but not impossible) would otherwise silently produce
        a None answer text three layers up in synthesizer.py."""
        from src import llm_router

        fake_response = MagicMock()
        fake_response.choices = [MagicMock(message=MagicMock(content=None))]
        fake_client = MagicMock()
        fake_client.chat.completions.create = AsyncMock(return_value=fake_response)

        llm_router._openai_llm_client = None
        with (
            patch.object(llm_router, "_get_openai_llm_client", return_value=fake_client),
            pytest.raises(ValueError, match="no text content"),
        ):
            await llm_router._complete_openai("prompt", 500)


class TestGeminiProvider:
    @pytest.mark.asyncio
    async def test_extracts_text_from_response(self):
        from src import llm_router

        fake_response = MagicMock()
        fake_response.text = "gemini's answer"
        fake_models = MagicMock()
        fake_models.generate_content = AsyncMock(return_value=fake_response)
        fake_client = MagicMock()
        fake_client.aio.models = fake_models

        llm_router._gemini_client = None
        with patch.object(llm_router, "_get_gemini_client", return_value=fake_client):
            result = await llm_router._complete_gemini("prompt", 500)

        assert result == "gemini's answer"

    def test_retryable_predicate_matches_server_error(self):
        from google.genai import errors
        from src.llm_router import _is_retryable_gemini_error

        server_error = errors.ServerError(500, {"error": {"message": "internal"}})
        assert _is_retryable_gemini_error(server_error) is True

    def test_retryable_predicate_matches_429_client_error(self):
        from google.genai import errors
        from src.llm_router import _is_retryable_gemini_error

        rate_limited = errors.ClientError(429, {"error": {"message": "rate limited"}})
        assert _is_retryable_gemini_error(rate_limited) is True

    def test_retryable_predicate_rejects_400_client_error(self):
        from google.genai import errors
        from src.llm_router import _is_retryable_gemini_error

        bad_request = errors.ClientError(400, {"error": {"message": "bad request"}})
        assert _is_retryable_gemini_error(bad_request) is False
