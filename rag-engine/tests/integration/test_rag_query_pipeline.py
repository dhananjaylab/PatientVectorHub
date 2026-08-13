"""
RAG Query Engine integration test (Phase 7) — runs against real services
(the local Docker Compose stack, or the equivalent CI services in
.github/workflows/ci.yml), not mocks, for the two surfaces this phase
introduces that no prior test has exercised for real: Anthropic's
messages.create() call shape/response parsing, and — end to end — a real
embedded query actually retrieving a real Weaviate-stored chunk and
getting synthesized into a cited answer.

Scoped to `rag-engine` only for its own sys.path.insert (not mixing
`rag-engine` + `vector-store` + `api-gateway` in one file's sys.path) —
same reasoning docs/PHASE_6_IMPLEMENTATION_PLAN.md gives for
test_vector_store_layer.py staying scoped to `vector-store` alone.
Unlike that file's era, this now works cleanly even though
rag-engine/src/retriever.py and synthesizer.py both cross-import
vector_store — see tests/conftest.py's _ensure_cross_package_alias()
(Phase 7 addition) for why the previously-flagged collision no longer
applies here.

TestRAGSynthesizerLive needs only ANTHROPIC_API_KEY (self-skips without
it) — this is the single highest-value previously-unverified surface:
no existing test calls a real LLM completion API at all.
TestFullQueryPipelineLive needs both ANTHROPIC_API_KEY and
OPENAI_API_KEY (self-skips without either) — proves retrieve() + a real
Weaviate round-trip + synthesize() work together, not just each piece in
isolation.
"""

import os
import sys
import uuid
from pathlib import Path

import pytest
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env")
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "rag-engine"))

TENANT_ID = "00000000-0000-0000-0000-000000000001"  # seeded by scripts/seed_data.py
FAKE_VECTOR_DIM = int(os.getenv("EMBEDDING_DIMENSIONS", "1536"))


def _fake_vector(seed: int) -> list[float]:
    """Same deterministic, non-embedding vector helper as
    test_vector_store_layer.py — good enough to prove a chunk actually
    round-trips through Weaviate; the thing under test here is retrieval
    + synthesis wiring and the Anthropic call shape, not embedding
    quality (already covered by ADR-009's tests)."""
    return [((seed + i) % 97) / 97.0 for i in range(FAKE_VECTOR_DIM)]


@pytest.mark.integration
@pytest.mark.skipif(
    not os.getenv("ANTHROPIC_API_KEY"),
    reason="requires a real ANTHROPIC_API_KEY for the LLM synthesis call",
)
class TestRAGSynthesizerLive:
    @pytest.mark.asyncio
    async def test_synthesize_against_real_anthropic_api(self):
        """Proves messages.create()'s exact call shape and response
        parsing (message.content[0].text) against the real API — the
        one thing every mock-based unit test in test_llm_router.py and
        test_rag_synthesizer.py cannot prove by construction."""
        from vector_store.interface import SearchResult
        from src.synthesizer import RAGSynthesizer

        chunks = [
            SearchResult(
                doc_id="d-live-1",
                chunk_text="Patient HbA1c 8.4%, consistent with type 2 diabetes mellitus.",
                score=0.95,
                document_type="lab_result",
            ),
            SearchResult(
                doc_id="d-live-2",
                chunk_text="Metformin 1000mg prescribed twice daily.",
                score=0.88,
                document_type="prescription",
            ),
        ]

        synth = RAGSynthesizer()
        result = await synth.synthesize(
            query="What is the patient's HbA1c and current diabetes treatment?",
            chunks=chunks,
        )

        assert isinstance(result["answer"], str)
        assert len(result["answer"]) > 0
        # Not asserting exact citation content — a real model's output is
        # not that deterministic — only that the plumbing (prompt in,
        # non-empty grounded answer out, citation extraction runs without
        # error) actually works end to end.
        assert isinstance(result["citations"], list)


@pytest.mark.integration
@pytest.mark.skipif(
    not (os.getenv("ANTHROPIC_API_KEY") and os.getenv("OPENAI_API_KEY")),
    reason="requires real ANTHROPIC_API_KEY and OPENAI_API_KEY for the full pipeline",
)
class TestFullQueryPipelineLive:
    @pytest.mark.asyncio
    async def test_retrieve_then_synthesize_end_to_end(self):
        """Seeds one real chunk into Weaviate (fake vector — see
        _fake_vector), then runs the actual Phase 7 pipeline against it:
        real query embedding (OpenAI) -> real hybrid search (Weaviate) ->
        real synthesis (Anthropic). This is the first test in the repo
        that exercises retriever.retrieve() at all — every other
        reference to it (test_retriever.py) mocks both embed_query() and
        get_store()."""
        from vector_store.interface import Chunk
        from src.retriever import retrieve
        from src.synthesizer import RAGSynthesizer
        from vector_store.weaviate_store import WeaviateStore

        doc_id = str(uuid.uuid4())
        vector = _fake_vector(seed=42)
        store = WeaviateStore(TENANT_ID)
        chunk = Chunk(
            text="Patient shows elevated HbA1c consistent with type 2 diabetes.",
            index=0,
            metadata={
                "document_type": "lab_result",
                "patient_id_hash": "hash-e2e-phase7",
            },
        )
        try:
            await store.upsert(doc_id, [chunk], [vector])

            # NOTE: retrieve() embeds body.query_text with the REAL OpenAI
            # embedder (ADR-009 default), which will NOT be the same
            # vector as `vector` above — the search below relies on
            # Weaviate's BM25 half of hybrid search to still surface this
            # chunk via keyword match ("HbA1c", "diabetes"), same as a
            # real query would, rather than dense-vector similarity to an
            # arbitrary fake vector.
            chunks = await retrieve(TENANT_ID, "patient HbA1c diabetes management", top_k=5)
            assert any(c.doc_id == doc_id for c in chunks)

            synth = RAGSynthesizer()
            result = await synth.synthesize(query="What does the HbA1c indicate?", chunks=chunks)
            assert len(result["answer"]) > 0
        finally:
            await store.delete(doc_id)
            store.close()
