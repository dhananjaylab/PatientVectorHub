"""Pydantic request/response models for POST /v1/query (Phase 7).

llm_provider defaults to None rather than a hardcoded "anthropic" — the
actual default lives in rag-engine/src/config.py's LLM_DEFAULT_PROVIDER
(rag_engine.llm_router.LLMRouter.complete() resolves None to that
setting). Duplicating "anthropic" as a second default here would let the
two drift out of sync silently.

filters only exposes document_types for now, matching what
vector-store/src/weaviate_store.py's _build_filter() actually implements
— see that module's docstring and docs/adr/ADR-014-rag-query-engine.md
§3 for why date_range/cohort_filter (present in the original doc-32
sketch) aren't in this schema yet.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class QueryFilters(BaseModel):
    document_types: list[str] | None = None


class QueryRequest(BaseModel):
    query_text: str = Field(..., min_length=3, max_length=2000)
    filters: QueryFilters | None = None
    top_k: int = Field(default=10, ge=1, le=50)
    llm_provider: str | None = Field(default=None, pattern="^(openai|anthropic|gemini)$")


class QueryResultItem(BaseModel):
    doc_id: str
    chunk_text: str
    score: float
    document_type: str


class Citation(BaseModel):
    index: int
    doc_id: str
    document_type: str


class QueryResponse(BaseModel):
    query_id: str
    answer: str
    citations: list[Citation]
    results: list[QueryResultItem]
    latency_ms: int
