"""
PatientVectorHub — RAG query route (Phase 7; rate limit added Phase 8 /
ADR-015).

POST /v1/query is the first real caller of vector_store.interface.search()
— ADR-013 §1 named Phase 7 as that caller when it added the required
query_vector parameter. This route: embeds + retrieves via
rag_engine.retriever.retrieve(), synthesizes a cited answer via
rag_engine.synthesizer.RAGSynthesizer, writes one query_logs row
(crud.log_query — defined since Phase 4/6's db/crud.py, unused until now)
and one audit_logs row (crud.write_audit_log(action="document_query")),
matching routers/ingest.py's existing document_ingest audit pattern
exactly.

Retrieval and synthesis failures are wrapped in errors.py's existing
QueryError/LLMError classes rather than left as raw exceptions — their
contract was confirmed via tests/unit/test_errors.py, since errors.py's
own source came through unreadable in the repo dump (same issue main.py
and config.py hit in Phase 4 — see MANUAL_INTEGRATION_NOTES.md). Both
classes already existed before this phase touched anything, apparently
provisioned for exactly this use.

Requires rag_engine and vector_store importable from this process — same
cross-package shape ingestion/src/workers/batch_worker.py already has
with vector_store since Phase 4. See MANUAL_INTEGRATION_NOTES.md for the
Dockerfile / local-dev implications this adds for api-gateway
specifically (it didn't need either package before this route existed).

Phase 8 addition: `@limiter.limit("1000/minute")` (doc 09's exact value
for this route) — needed a new `response: Response` param alongside the
`request: Request` this route already had; see
middleware/rate_limit.py's docstring for why the decorator requires both.
Nothing else in this file's logic changed.
"""

from __future__ import annotations

import time
import uuid

from fastapi import APIRouter, Depends, Response
from rag_engine.config import settings as rag_settings
from rag_engine.retriever import retrieve
from rag_engine.synthesizer import RAGSynthesizer
from starlette.requests import Request

from ..db import crud
from ..deps import get_current_user, get_db
from ..errors import LLMError, QueryError
from ..middleware.rate_limit import limiter
from ..middleware.rbac import require_min_role
from ..schemas.query import Citation, QueryRequest, QueryResponse, QueryResultItem

router = APIRouter()

# Stateless — safe as a module-level singleton (see llm_router.py's
# LLMRouter docstring). Individual provider clients inside it are still
# each lazily constructed on first real call.
_synthesizer = RAGSynthesizer()


@router.post("", response_model=QueryResponse, dependencies=[require_min_role("analyst")])
@limiter.limit("1000/minute")  # doc 09: POST /v1/query — 1000/min
async def rag_query(
    body: QueryRequest,
    request: Request,
    response: Response,
    db=Depends(get_db),
    user=Depends(get_current_user),
) -> QueryResponse:
    start = time.perf_counter()
    tenant_id = user["tenant_id"]
    filters = body.filters.model_dump(exclude_none=True) if body.filters else None

    # QueryError/LLMError already exist in errors.py's hierarchy (see
    # tests/unit/test_errors.py — QueryError status 500/"QUERY_ERROR",
    # LLMError status 503) and main.py already registers a PVHError
    # exception handler. Retrieval and synthesis failures are wrapped
    # into those rather than left as raw RuntimeError/SDK exceptions, so
    # a Weaviate outage and an Anthropic outage don't both collapse into
    # an identical unstructured 500.
    try:
        chunks = await retrieve(tenant_id, body.query_text, top_k=body.top_k, filters=filters)
    except Exception as exc:
        raise QueryError("Retrieval failed", detail=str(exc)) from exc

    try:
        synthesis = await _synthesizer.synthesize(
            query=body.query_text, chunks=chunks, provider=body.llm_provider
        )
    except Exception as exc:
        raise LLMError("Answer synthesis failed", detail=str(exc)) from exc

    latency_ms = int((time.perf_counter() - start) * 1000)

    # Non-fatal by convention elsewhere in this codebase (see
    # dual_write_store.py's secondary-write handling) would be the wrong
    # call here — query_logs/audit_logs writes for document_query are the
    # same kind of compliance-relevant record document_ingest's audit
    # write already is, so a failure here should surface, not be
    # swallowed. No try/except added — an exception here propagates to
    # main.py's 500 handler like any other route failure would.
    await crud.log_query(
        db,
        user_id=user["user_id"],
        query_text=body.query_text,
        result_count=len(chunks),
        latency_ms=latency_ms,
        model_version=rag_settings.EMBEDDING_MODEL_VERSION,
    )
    await crud.write_audit_log(
        db,
        action="document_query",
        user_id=user["user_id"],
        metadata={
            "result_count": len(chunks),
            "latency_ms": latency_ms,
            "top_k": body.top_k,
        },
    )

    return QueryResponse(
        query_id=str(uuid.uuid4()),
        answer=synthesis["answer"],
        citations=[Citation(**c) for c in synthesis["citations"]],
        results=[
            QueryResultItem(
                doc_id=c.doc_id,
                chunk_text=c.chunk_text,
                score=c.score,
                document_type=c.document_type,
            )
            for c in chunks
        ],
        latency_ms=latency_ms,
    )
