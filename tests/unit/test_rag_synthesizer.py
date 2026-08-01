"""
Unit tests for rag-engine/src/synthesizer.py (Phase 7). LLMRouter is
mocked via conftest.py's mock_llm fixture — no live LLM call needed to
run this file. Needs vector_store importable (SearchResult) — see
tests/conftest.py's _ensure_cross_package_alias().
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "rag-engine"))

import pytest


def _make_chunks():
    from vector_store.interface import SearchResult

    return [
        SearchResult(
            doc_id="d-001",
            chunk_text="Patient HbA1c 8.4% elevated — type 2 DM.",
            score=0.95,
            document_type="lab_result",
        ),
        SearchResult(
            doc_id="d-002",
            chunk_text="Prescribed metformin 1000mg twice daily.",
            score=0.88,
            document_type="prescription",
        ),
    ]


class TestSynthesize:
    @pytest.mark.asyncio
    async def test_empty_chunks_short_circuits_without_calling_llm(self, mock_llm):
        from src.synthesizer import RAGSynthesizer

        synth = RAGSynthesizer(llm_router=mock_llm)
        result = await synth.synthesize(query="anything", chunks=[])

        mock_llm.complete.assert_not_called()
        assert result["citations"] == []
        assert "No relevant documents" in result["answer"]

    @pytest.mark.asyncio
    async def test_builds_prompt_with_numbered_excerpts(self, mock_llm):
        from src.synthesizer import RAGSynthesizer

        synth = RAGSynthesizer(llm_router=mock_llm)
        await synth.synthesize(query="diabetes management", chunks=_make_chunks())

        prompt = mock_llm.complete.call_args[0][0]
        assert "[1] (lab_result): Patient HbA1c 8.4%" in prompt
        assert "[2] (prescription): Prescribed metformin" in prompt
        assert "diabetes management" in prompt

    @pytest.mark.asyncio
    async def test_extracts_citations_referenced_in_answer(self, mock_llm):
        from src.synthesizer import RAGSynthesizer

        # mock_llm's canned answer (conftest.py) references [1] and [2]
        synth = RAGSynthesizer(llm_router=mock_llm)
        result = await synth.synthesize(query="q", chunks=_make_chunks())

        indices = sorted(c["index"] for c in result["citations"])
        assert indices == [1, 2]
        assert result["citations"][0]["doc_id"] == "d-001"
        assert result["citations"][1]["doc_id"] == "d-002"

    @pytest.mark.asyncio
    async def test_citation_index_out_of_range_is_dropped(self, mock_llm):
        from src.synthesizer import RAGSynthesizer

        mock_llm.complete.return_value = "Some answer citing [1] and a bogus [99]."
        synth = RAGSynthesizer(llm_router=mock_llm)
        result = await synth.synthesize(query="q", chunks=_make_chunks())

        assert [c["index"] for c in result["citations"]] == [1]

    @pytest.mark.asyncio
    async def test_provider_and_max_tokens_passed_through(self, mock_llm):
        from src.synthesizer import RAGSynthesizer

        synth = RAGSynthesizer(llm_router=mock_llm)
        await synth.synthesize(query="q", chunks=_make_chunks(), provider="openai", max_tokens=250)

        _, kwargs = mock_llm.complete.call_args
        assert kwargs["provider"] == "openai"
        assert kwargs["max_tokens"] == 250

    @pytest.mark.asyncio
    async def test_default_llm_router_is_constructed_when_none_given(self):
        from src.llm_router import LLMRouter
        from src.synthesizer import RAGSynthesizer

        synth = RAGSynthesizer()
        assert isinstance(synth.llm, LLMRouter)
