"""
RAGSynthesizer — builds the grounding prompt from retrieved chunks and
extracts [n]-style citations from the LLM's answer (Phase 7).

Prompt shape and citation-extraction approach follow the original doc-22
reference design (regex over [\\d+] markers the prompt asks the model to
emit) — that part of the design didn't need re-deciding, only the plumbing
around it (SearchResult from vector_store.interface instead of the old
docs' local dataclass; LLMRouter re-verified against currently-installed
SDKs — see llm_router.py).
"""

import re

from vector_store.interface import SearchResult

from .llm_router import LLMRouter

_PROMPT_TEMPLATE = """You are a clinical data analyst assistant. Use ONLY the provided patient document excerpts below to answer the question. Cite sources inline using [n], matching the excerpt numbers below. If the excerpts don't contain enough information to answer, say so explicitly rather than guessing.

Excerpts:
{context}

Question: {question}

Answer (cite sources inline as [1], [2], etc.; note if information is insufficient):"""

_MAX_CHUNK_CHARS = 400


class RAGSynthesizer:
    def __init__(self, llm_router: LLMRouter | None = None):
        self.llm = llm_router or LLMRouter()

    async def synthesize(
        self,
        query: str,
        chunks: list[SearchResult],
        provider: str | None = None,
        max_tokens: int | None = None,
    ) -> dict:
        """Returns {"answer": str, "citations": list[dict]}.

        Short-circuits without calling the LLM at all when chunks is
        empty — there is nothing to ground an answer in, and asking the
        model to answer anyway invites exactly the unsourced-guessing
        failure mode the prompt otherwise tries to prevent."""
        if not chunks:
            return {
                "answer": "No relevant documents were found for this query.",
                "citations": [],
            }

        context = "\n\n".join(
            f"[{i}] ({c.document_type or 'document'}): {c.chunk_text[:_MAX_CHUNK_CHARS]}"
            for i, c in enumerate(chunks, start=1)
        )
        prompt = _PROMPT_TEMPLATE.format(context=context, question=query)
        answer = await self.llm.complete(prompt, provider=provider, max_tokens=max_tokens)

        cited_indices = sorted({int(m) for m in re.findall(r"\[(\d+)\]", answer)})
        citations = [
            {
                "index": i,
                "doc_id": chunks[i - 1].doc_id,
                "document_type": chunks[i - 1].document_type,
            }
            for i in cited_indices
            if 1 <= i <= len(chunks)
        ]
        return {"answer": answer, "citations": citations}
