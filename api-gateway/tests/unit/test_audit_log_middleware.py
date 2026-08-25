"""
Unit tests for api-gateway/src/middleware/audit_log.py (Phase 10 / ADR-017).

Standalone-app pattern, matching tests/unit/test_query_router.py's own
established precedent: a small FastAPI app with a fake auth middleware
standing in for KeycloakJWTMiddleware, so these tests exercise
AuditLogMiddleware's real dispatch() logic without needing main.py's
full lifespan (Kafka producer, Vault, DB pool) or a live Postgres.
crud.write_audit_log and db/session.get_tenant_session are mocked at
the point AuditLogMiddleware imports them (inside the function, not
module scope — see that module's own docstring for why), matching this
codebase's own established mocking granularity.
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI, HTTPException
from httpx import ASGITransport, AsyncClient
from starlette.middleware.base import BaseHTTPMiddleware

from src.middleware.audit_log import AuditLogMiddleware


def _build_app(*, tenant_id: str | None, role: str = "readonly", route_status: int = 403):
    app = FastAPI()

    class _FakeAuthMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request, call_next):
            request.state.user_id = "user-1" if tenant_id else None
            request.state.tenant_id = tenant_id
            request.state.role = role
            request.state.api_key_id = None
            request.state.request_id = "req-fixed-for-test"
            return await call_next(request)

    # AuditLogMiddleware must be OUTERMOST (added last) to see the final
    # status_code and to have request.state already populated by the
    # fake auth middleware — matches main.py's real registration order.
    app.add_middleware(_FakeAuthMiddleware)
    app.add_middleware(AuditLogMiddleware)

    @app.get("/protected")
    async def protected():
        raise HTTPException(status_code=route_status, detail="nope")

    @app.get("/ok")
    async def ok():
        return {"status": "ok"}

    return app


@pytest.fixture()
def mock_write_audit_log():
    with patch("src.db.crud.write_audit_log", new_callable=AsyncMock) as mock_write:
        yield mock_write


@pytest.fixture()
def mock_get_tenant_session():
    @asynccontextmanager
    async def _fake_session(tenant_id: str):
        yield AsyncMock()

    with patch("src.db.session.get_tenant_session", side_effect=_fake_session) as mock_get:
        yield mock_get


class TestIpAddressPopulation:
    @pytest.mark.asyncio
    async def test_sets_request_state_ip_address_before_route_runs(self):
        app = _build_app(tenant_id="tenant-a", route_status=403)
        captured = {}

        @app.middleware("http")
        async def _capture(request, call_next):
            response = await call_next(request)
            captured["ip"] = getattr(request.state, "ip_address", "MISSING")
            return response

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            with patch("src.db.crud.write_audit_log", new_callable=AsyncMock), patch(
                "src.db.session.get_tenant_session"
            ):
                await client.get("/protected")

        # httpx's ASGITransport sets a client tuple; either a real value
        # or None is acceptable here — the point is the attribute exists
        # at all (was actually set), not left unset by dispatch().
        assert "ip" in captured
        assert captured["ip"] != "MISSING"


class TestAccessDeniedLogging:
    @pytest.mark.asyncio
    async def test_writes_access_denied_row_on_403_with_known_tenant(
        self, mock_write_audit_log, mock_get_tenant_session
    ):
        app = _build_app(tenant_id="tenant-a", role="readonly", route_status=403)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/protected")

        assert response.status_code == 403
        mock_get_tenant_session.assert_called_once_with("tenant-a")
        mock_write_audit_log.assert_called_once()
        _, kwargs = mock_write_audit_log.call_args
        assert kwargs["action"] == "access_denied"
        assert kwargs["status_code"] == 403
        assert kwargs["request_id"] == "req-fixed-for-test"
        assert kwargs["metadata"]["path"] == "/protected"
        assert kwargs["metadata"]["role"] == "readonly"

    @pytest.mark.asyncio
    async def test_does_not_write_to_audit_logs_on_bare_401_with_no_tenant_context(
        self, mock_write_audit_log, mock_get_tenant_session
    ):
        """The RLS-driven boundary this module's docstring documents:
        no tenant_id means no valid audit_logs row can be scoped, so
        this must not even attempt the write, let alone raise."""
        app = _build_app(tenant_id=None, route_status=401)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/protected")

        assert response.status_code == 401
        mock_write_audit_log.assert_not_called()
        mock_get_tenant_session.assert_not_called()

    @pytest.mark.asyncio
    async def test_does_not_write_for_successful_requests(
        self, mock_write_audit_log, mock_get_tenant_session
    ):
        app = _build_app(tenant_id="tenant-a", route_status=403)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/ok")

        assert response.status_code == 200
        mock_write_audit_log.assert_not_called()

    @pytest.mark.asyncio
    async def test_audit_write_failure_does_not_turn_403_into_500(
        self, mock_get_tenant_session
    ):
        """The response was already correctly built (403) before the
        audit side-effect runs -- a DB hiccup while logging must not
        change what the caller sees."""
        app = _build_app(tenant_id="tenant-a", route_status=403)
        transport = ASGITransport(app=app)
        with patch(
            "src.db.crud.write_audit_log",
            new_callable=AsyncMock,
            side_effect=Exception("db exploded"),
        ):
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.get("/protected")

        assert response.status_code == 403  # not 500
