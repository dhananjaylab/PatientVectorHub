"""
Unit tests for api-gateway/src/routers/audit.py (Phase 8 / ADR-015).

Standalone-app harness mirrors tests/unit/test_query_router.py's
established pattern exactly (a fake auth middleware populating
request.state directly, since that — not the get_current_user
*dependency* — is what middleware.rbac's require_role()/
require_min_role() actually read; see that file's own docstring for why
overriding just the dependency is insufficient). crud.list_audit_logs
and crud.write_audit_log are mocked throughout — no real DB needed to
run this file.
"""

import datetime
import uuid
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient


def _build_app(role: str = "admin", tenant_id: str = "tenant-a", user_id: str = "user-1"):
    from src.deps import get_db
    from src.routers.audit import router
    from starlette.middleware.base import BaseHTTPMiddleware

    app = FastAPI()

    class _FakeAuthMiddleware(BaseHTTPMiddleware):
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
    app.include_router(router, prefix="/v1/audit")

    async def _fake_get_db():
        yield AsyncMock()

    app.dependency_overrides[get_db] = _fake_get_db
    return app


def _mock_log_row(**overrides) -> dict:
    row = {
        "id": uuid.uuid4(),
        "user_id": uuid.uuid4(),
        "action": "document_query",
        "patient_id": None,
        "ip_address": "10.0.0.5",
        "request_id": "req-abc",
        "status_code": 200,
        "created_at": datetime.datetime(2026, 8, 15, 12, 0, 0, tzinfo=datetime.timezone.utc),
    }
    row.update(overrides)
    return row


class TestGetAuditLogsRoleScoping:
    @pytest.mark.asyncio
    async def test_admin_sees_any_requested_user_id_unscoped(self):
        app = _build_app(role="admin", user_id="admin-1")
        with patch(
            "src.routers.audit.crud.list_audit_logs",
            new=AsyncMock(return_value={"logs": [], "total": 0}),
        ) as mocked:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
                resp = await c.get("/v1/audit/logs", params={"user_id": "someone-else"})
        assert resp.status_code == 200
        assert mocked.call_args.kwargs["user_id"] == "someone-else"

    @pytest.mark.asyncio
    async def test_auditor_sees_any_requested_user_id_unscoped(self):
        app = _build_app(role="auditor", user_id="auditor-1")
        with patch(
            "src.routers.audit.crud.list_audit_logs",
            new=AsyncMock(return_value={"logs": [], "total": 0}),
        ) as mocked:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
                resp = await c.get("/v1/audit/logs", params={"user_id": "someone-else"})
        assert resp.status_code == 200
        assert mocked.call_args.kwargs["user_id"] == "someone-else"

    @pytest.mark.asyncio
    async def test_analyst_is_force_scoped_to_own_user_id(self):
        """doc 05: 'analyst — Can read audit logs for own queries only.'
        Even an explicit attempt to filter by a different user_id gets
        silently overridden, not rejected — see _resolve_effective_user_id's
        docstring for why this is filtering-not-erroring."""
        app = _build_app(role="analyst", user_id="analyst-42")
        with patch(
            "src.routers.audit.crud.list_audit_logs",
            new=AsyncMock(return_value={"logs": [], "total": 0}),
        ) as mocked:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
                resp = await c.get("/v1/audit/logs", params={"user_id": "someone-else"})
        assert resp.status_code == 200
        assert mocked.call_args.kwargs["user_id"] == "analyst-42"

    @pytest.mark.asyncio
    async def test_engineer_is_force_scoped_to_own_user_id(self):
        app = _build_app(role="engineer", user_id="engineer-7")
        with patch(
            "src.routers.audit.crud.list_audit_logs",
            new=AsyncMock(return_value={"logs": [], "total": 0}),
        ) as mocked:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
                await c.get("/v1/audit/logs")
        assert mocked.call_args.kwargs["user_id"] == "engineer-7"

    @pytest.mark.asyncio
    async def test_readonly_is_rejected_403(self):
        app = _build_app(role="readonly")
        with patch("src.routers.audit.crud.list_audit_logs", new=AsyncMock()):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
                resp = await c.get("/v1/audit/logs")
        assert resp.status_code == 403


class TestGetAuditLogsFiltersAndPagination:
    @pytest.mark.asyncio
    async def test_all_filters_passed_through_to_crud(self):
        app = _build_app(role="admin")
        with patch(
            "src.routers.audit.crud.list_audit_logs",
            new=AsyncMock(return_value={"logs": [], "total": 0}),
        ) as mocked:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
                await c.get(
                    "/v1/audit/logs",
                    params={
                        "action": "phi_reveal",
                        "patient_id": "11111111-1111-1111-1111-111111111111",
                        "from_ts": "2026-08-01T00:00:00Z",
                        "to_ts": "2026-08-15T00:00:00Z",
                        "limit": 25,
                        "offset": 50,
                    },
                )
        kwargs = mocked.call_args.kwargs
        assert kwargs["action"] == "phi_reveal"
        assert kwargs["patient_id"] == "11111111-1111-1111-1111-111111111111"
        assert kwargs["from_ts"] == "2026-08-01T00:00:00Z"
        assert kwargs["to_ts"] == "2026-08-15T00:00:00Z"
        assert kwargs["limit"] == 25
        assert kwargs["offset"] == 50

    @pytest.mark.asyncio
    async def test_response_envelope_shape(self):
        app = _build_app(role="admin")
        rows = [_mock_log_row(), _mock_log_row(action="phi_reveal")]
        with patch(
            "src.routers.audit.crud.list_audit_logs",
            new=AsyncMock(return_value={"logs": rows, "total": 2}),
        ):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
                resp = await c.get("/v1/audit/logs")
        body = resp.json()
        assert body["total"] == 2
        assert body["limit"] == 50
        assert body["offset"] == 0
        assert len(body["logs"]) == 2
        # UUID / datetime fields must come back as plain strings, not
        # raw uuid.UUID/datetime reprs — exercises _serialize_log_row.
        assert isinstance(body["logs"][0]["id"], str)
        assert isinstance(body["logs"][0]["user_id"], str)
        assert body["logs"][0]["created_at"] == "2026-08-15T12:00:00+00:00"

    @pytest.mark.asyncio
    async def test_limit_over_200_is_422(self):
        app = _build_app(role="admin")
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
            resp = await c.get("/v1/audit/logs", params={"limit": 500})
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_negative_offset_is_422(self):
        app = _build_app(role="admin")
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
            resp = await c.get("/v1/audit/logs", params={"offset": -1})
        assert resp.status_code == 422


class TestExportAuditLogs:
    @pytest.mark.asyncio
    async def test_admin_can_export(self):
        app = _build_app(role="admin", user_id="admin-1")
        rows = [_mock_log_row()]
        with (
            patch(
                "src.routers.audit.crud.list_audit_logs",
                new=AsyncMock(return_value={"logs": rows, "total": 1}),
            ),
            patch("src.routers.audit.crud.write_audit_log", new=AsyncMock()) as mocked_write,
        ):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
                resp = await c.get("/v1/audit/logs/export")
        assert resp.status_code == 200
        mocked_write.assert_called_once()
        assert mocked_write.call_args.kwargs["action"] == "data_export"
        assert mocked_write.call_args.kwargs["user_id"] == "admin-1"

    @pytest.mark.asyncio
    async def test_auditor_can_export(self):
        app = _build_app(role="auditor")
        with (
            patch(
                "src.routers.audit.crud.list_audit_logs",
                new=AsyncMock(return_value={"logs": [], "total": 0}),
            ),
            patch("src.routers.audit.crud.write_audit_log", new=AsyncMock()),
        ):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
                resp = await c.get("/v1/audit/logs/export")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_analyst_cannot_export(self):
        app = _build_app(role="analyst")
        with patch("src.routers.audit.crud.list_audit_logs", new=AsyncMock()):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
                resp = await c.get("/v1/audit/logs/export")
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_engineer_cannot_export(self):
        app = _build_app(role="engineer")
        with patch("src.routers.audit.crud.list_audit_logs", new=AsyncMock()):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
                resp = await c.get("/v1/audit/logs/export")
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_readonly_cannot_export(self):
        app = _build_app(role="readonly")
        with patch("src.routers.audit.crud.list_audit_logs", new=AsyncMock()):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
                resp = await c.get("/v1/audit/logs/export")
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_csv_is_the_default_format(self):
        app = _build_app(role="admin")
        rows = [_mock_log_row(action="phi_reveal", patient_id=str(uuid.uuid4()))]
        with (
            patch(
                "src.routers.audit.crud.list_audit_logs",
                new=AsyncMock(return_value={"logs": rows, "total": 1}),
            ),
            patch("src.routers.audit.crud.write_audit_log", new=AsyncMock()),
        ):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
                resp = await c.get("/v1/audit/logs/export")
        assert resp.headers["content-type"].startswith("text/csv")
        assert "attachment" in resp.headers["content-disposition"]
        assert resp.headers["content-disposition"].endswith('.csv"')
        body_text = resp.text
        assert "id,user_id,action,patient_id,ip_address,request_id,status_code,created_at" in body_text
        assert "phi_reveal" in body_text

    @pytest.mark.asyncio
    async def test_csv_export_with_zero_rows_still_has_header(self):
        app = _build_app(role="admin")
        with (
            patch(
                "src.routers.audit.crud.list_audit_logs",
                new=AsyncMock(return_value={"logs": [], "total": 0}),
            ),
            patch("src.routers.audit.crud.write_audit_log", new=AsyncMock()),
        ):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
                resp = await c.get("/v1/audit/logs/export")
        assert resp.status_code == 200
        assert "id,user_id,action" in resp.text

    @pytest.mark.asyncio
    async def test_json_format(self):
        app = _build_app(role="admin")
        rows = [_mock_log_row()]
        with (
            patch(
                "src.routers.audit.crud.list_audit_logs",
                new=AsyncMock(return_value={"logs": rows, "total": 1}),
            ),
            patch("src.routers.audit.crud.write_audit_log", new=AsyncMock()),
        ):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
                resp = await c.get("/v1/audit/logs/export", params={"format": "json"})
        assert resp.headers["content-type"].startswith("application/json")
        assert resp.headers["content-disposition"].endswith('.json"')
        body = resp.json()
        assert body["exported"] == 1
        assert body["logs"][0]["action"] == "document_query"

    @pytest.mark.asyncio
    async def test_invalid_format_is_422(self):
        app = _build_app(role="admin")
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
            resp = await c.get("/v1/audit/logs/export", params={"format": "xml"})
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_export_metadata_records_row_count_and_filters(self):
        app = _build_app(role="admin", user_id="admin-9")
        rows = [_mock_log_row(), _mock_log_row()]
        with (
            patch(
                "src.routers.audit.crud.list_audit_logs",
                new=AsyncMock(return_value={"logs": rows, "total": 2}),
            ),
            patch("src.routers.audit.crud.write_audit_log", new=AsyncMock()) as mocked_write,
        ):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
                await c.get(
                    "/v1/audit/logs/export",
                    params={"format": "json", "action": "phi_reveal"},
                )
        metadata = mocked_write.call_args.kwargs["metadata"]
        assert metadata["row_count"] == 2
        assert metadata["export_format"] == "json"
        assert metadata["truncated"] is False
        assert metadata["filters"]["action"] == "phi_reveal"
