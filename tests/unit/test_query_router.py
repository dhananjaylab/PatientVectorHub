"""
Unit tests for api-gateway/src/routers/query.py (Phase 7) — POST /v1/query.

Builds a minimal standalone FastAPI app around just the query router
(dependency_overrides for get_db/get_current_user), rather than the full
main.py app tests/conftest.py's `test_app` fixture wires up — this
router is the first one in the whole codebase whose import chain pulls
in rag_engine (and therefore anthropic/openai/google-genai/
weaviate-client/qdrant-client), and isolating it keeps this file's
failure modes about query.py's own logic, not main.py's full lifespan
(Kafka producer, Vault, DB pool). retrieve() and RAGSynthesizer are both
mocked at the module level query.py imported them into — no live vector
store or LLM call needed to run this file.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "api-gateway"))

from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient


def _build_app(role: str = "analyst", tenant_id: str = "tenant-a", user_id: str = "user-1"):
    from src.deps import get_db
    from src.routers.query import router
    from starlette.middleware.base import BaseHTTPMiddleware

    app = FastAPI()

    class _FakeAuthMiddleware(BaseHTTPMiddleware):
        """Stands in for middleware.auth.KeycloakJWTMiddleware, which is
        what actually populates request.state in production — both
        get_current_user() and middleware.rbac.require_min_role() read
        request.state directly, not each other. Overriding just the
        get_current_user *dependency* (an earlier version of this test
        did exactly that) leaves request.state untouched, so
        require_min_role still sees the default "readonly" role and
        every request 403s regardless of the role a test asks for —
        caught by actually running this against the real router, not by
        inspection."""

        async def dispatch(self, request, call_next):
            request.state.user_id = user_id
            request.state.tenant_id = tenant_id
            request.state.role = role
            request.state.email = None
            request.state.auth_method = "jwt"
            request.state.api_key_id = None
            request.state.scopes = []
            return await call_next(request)

    app.add_middleware(_FakeAuthMiddleware)
    app.include_router(router, prefix="/v1/query")

    async def _fake_get_db():
        yield AsyncMock()

    app.dependency_overrides[get_db] = _fake_get_db
    return app


def _mock_search_result(
    doc_id="d-001",
    chunk_text="HbA1c 8.4% elevated",
    score=0.95,
    document_type="lab_result",
):
    from vector_store.interface import SearchResult

    return SearchResult(
        doc_id=doc_id, chunk_text=chunk_text, score=score, document_type=document_type
    )


class TestRAGQueryRoute:
    @pytest.mark.asyncio
    async def test_analyst_gets_200_with_answer_and_citations(self):
        app = _build_app(role="analyst")
        chunks = [_mock_search_result()]

        with (
            patch("src.routers.query.retrieve", new=AsyncMock(return_value=chunks)),
            patch(
                "src.routers.query._synthesizer.synthesize",
                new=AsyncMock(
                    return_value={
                        "answer": "Elevated HbA1c [1].",
                        "citations": [
                            {
                                "index": 1,
                                "doc_id": "d-001",
                                "document_type": "lab_result",
                            }
                        ],
                    }
                ),
            ),
            patch("src.routers.query.crud.log_query", new=AsyncMock()),
            patch("src.routers.query.crud.write_audit_log", new=AsyncMock()),
        ):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
                resp = await c.post(
                    "/v1/query",
                    json={"query_text": "HbA1c elevated diabetes", "top_k": 5},
                )

        assert resp.status_code == 200
        body = resp.json()
        assert body["answer"] == "Elevated HbA1c [1]."
        assert len(body["results"]) == 1
        assert body["results"][0]["doc_id"] == "d-001"
        assert len(body["citations"]) == 1
        assert body["latency_ms"] >= 0

    @pytest.mark.asyncio
    async def test_readonly_role_is_rejected_403(self):
        app = _build_app(role="readonly")

        with (
            patch("src.routers.query.retrieve", new=AsyncMock(return_value=[])),
            patch("src.routers.query._synthesizer.synthesize", new=AsyncMock()),
        ):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
                resp = await c.post("/v1/query", json={"query_text": "anything at all", "top_k": 5})

        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_auditor_role_is_rejected_403(self):
        """auditor (level 1) is below analyst (level 2) in the role
        hierarchy — matches doc09's original API contract (analyst+)."""
        app = _build_app(role="auditor")

        with patch("src.routers.query.retrieve", new=AsyncMock(return_value=[])):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
                resp = await c.post("/v1/query", json={"query_text": "anything at all", "top_k": 5})

        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_engineer_role_is_allowed(self):
        """engineer (level 3) is above analyst (level 2) — require_min_role
        is a floor, not an exact match."""
        app = _build_app(role="engineer")

        with (
            patch("src.routers.query.retrieve", new=AsyncMock(return_value=[])),
            patch(
                "src.routers.query._synthesizer.synthesize",
                new=AsyncMock(return_value={"answer": "No documents found.", "citations": []}),
            ),
            patch("src.routers.query.crud.log_query", new=AsyncMock()),
            patch("src.routers.query.crud.write_audit_log", new=AsyncMock()),
        ):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
                resp = await c.post("/v1/query", json={"query_text": "anything at all", "top_k": 5})

        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_query_text_too_short_is_422(self):
        app = _build_app(role="analyst")
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.post("/v1/query", json={"query_text": "hi", "top_k": 5})
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_top_k_over_fifty_is_422(self):
        app = _build_app(role="analyst")
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.post(
                "/v1/query", json={"query_text": "a valid clinical query", "top_k": 999}
            )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_retrieval_failure_raises_query_error(self):
        from src.errors import QueryError

        app = _build_app(role="analyst")
        with patch(
            "src.routers.query.retrieve",
            new=AsyncMock(side_effect=RuntimeError("weaviate down")),
        ):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
                with pytest.raises(QueryError):
                    await c.post(
                        "/v1/query",
                        json={"query_text": "a valid clinical query", "top_k": 5},
                    )

    @pytest.mark.asyncio
    async def test_synthesis_failure_raises_llm_error(self):
        from src.errors import LLMError

        app = _build_app(role="analyst")
        with (
            patch(
                "src.routers.query.retrieve",
                new=AsyncMock(return_value=[_mock_search_result()]),
            ),
            patch(
                "src.routers.query._synthesizer.synthesize",
                new=AsyncMock(side_effect=RuntimeError("anthropic down")),
            ),
        ):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
                with pytest.raises(LLMError):
                    await c.post(
                        "/v1/query",
                        json={"query_text": "a valid clinical query", "top_k": 5},
                    )

    @pytest.mark.asyncio
    async def test_writes_query_log_and_audit_log(self):
        app = _build_app(role="analyst", user_id="user-42")

        with (
            patch(
                "src.routers.query.retrieve",
                new=AsyncMock(return_value=[_mock_search_result()]),
            ),
            patch(
                "src.routers.query._synthesizer.synthesize",
                new=AsyncMock(return_value={"answer": "answer text", "citations": []}),
            ),
            patch("src.routers.query.crud.log_query", new=AsyncMock()) as mocked_log_query,
            patch("src.routers.query.crud.write_audit_log", new=AsyncMock()) as mocked_audit,
        ):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
                await c.post(
                    "/v1/query",
                    json={"query_text": "a valid clinical query", "top_k": 5},
                )

        mocked_log_query.assert_called_once()
        assert mocked_log_query.call_args.kwargs["user_id"] == "user-42"
        assert mocked_log_query.call_args.kwargs["result_count"] == 1

        mocked_audit.assert_called_once()
        assert mocked_audit.call_args.kwargs["action"] == "document_query"
        assert mocked_audit.call_args.kwargs["user_id"] == "user-42"
