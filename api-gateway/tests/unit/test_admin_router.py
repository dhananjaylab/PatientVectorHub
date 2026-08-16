"""
Unit tests for api-gateway/src/routers/admin.py.

This router had ZERO dedicated unit test coverage before Phase 8 — no
test_admin.py existed anywhere in the suite, despite create_key/
revoke_key/list_keys/get_users having shipped since Phase 3. This file
closes that gap (per this phase's "update tests for old and new changes"
requirement) and covers the new GET /vector-store/namespaces endpoint
(ADR-015). Same standalone-app harness as tests/unit/test_query_router.py
and tests/unit/test_audit_router.py — a fake auth middleware populating
request.state directly (what middleware.rbac's guards actually read),
not just overriding the get_current_user dependency.
"""

import datetime
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient


def _build_app(role: str = "admin", tenant_id: str = "tenant-a", user_id: str = "user-1"):
    from src.deps import get_db
    from src.routers.admin import router
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
    app.include_router(router, prefix="/v1/admin")

    async def _fake_get_db():
        yield AsyncMock()

    app.dependency_overrides[get_db] = _fake_get_db
    return app


NON_ADMIN_ROLES = ["engineer", "analyst", "auditor", "readonly"]
NON_ENGINEER_OR_ABOVE_ROLES = ["analyst", "auditor", "readonly"]


class TestCreateApiKey:
    @pytest.mark.asyncio
    async def test_admin_can_create_key(self):
        app = _build_app(role="admin", user_id="admin-1")
        create_result = {
            "key_id": "k-1", "key_plaintext": "pvh_secret123", "name": "svc-key",
            "scopes": ["query:read"], "expires_at": "2027-01-01T00:00:00+00:00",
        }
        with (
            patch(
                "src.routers.admin.crud.create_api_key", new=AsyncMock(return_value=create_result)
            ),
            patch("src.routers.admin.crud.write_audit_log", new=AsyncMock()) as mocked_audit,
        ):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
                resp = await c.post(
                    "/v1/admin/api-keys",
                    json={"name": "svc-key", "scopes": ["query:read"], "expires_days": 90},
                )
        assert resp.status_code == 201
        assert resp.json()["key_plaintext"] == "pvh_secret123"
        mocked_audit.assert_called_once()
        assert mocked_audit.call_args.kwargs["action"] == "api_key_create"
        assert mocked_audit.call_args.kwargs["user_id"] == "admin-1"

    @pytest.mark.asyncio
    @pytest.mark.parametrize("role", NON_ADMIN_ROLES)
    async def test_non_admin_roles_rejected_403(self, role):
        app = _build_app(role=role)
        with patch("src.routers.admin.crud.create_api_key", new=AsyncMock()):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
                resp = await c.post(
                    "/v1/admin/api-keys",
                    json={"name": "x", "scopes": ["query:read"], "expires_days": 90},
                )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_empty_scopes_list_is_422(self):
        app = _build_app(role="admin")
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
            resp = await c.post(
                "/v1/admin/api-keys", json={"name": "x", "scopes": [], "expires_days": 90}
            )
        assert resp.status_code == 422


class TestRevokeApiKey:
    @pytest.mark.asyncio
    async def test_admin_can_revoke_existing_key(self):
        app = _build_app(role="admin", user_id="admin-1")
        with (
            patch("src.routers.admin.crud.revoke_api_key", new=AsyncMock(return_value=True)),
            patch("src.routers.admin.crud.write_audit_log", new=AsyncMock()) as mocked_audit,
        ):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
                resp = await c.delete("/v1/admin/api-keys/k-1")
        assert resp.status_code == 204
        mocked_audit.assert_called_once()
        assert mocked_audit.call_args.kwargs["action"] == "api_key_revoke"

    @pytest.mark.asyncio
    async def test_revoking_nonexistent_key_is_404(self):
        app = _build_app(role="admin")
        with patch("src.routers.admin.crud.revoke_api_key", new=AsyncMock(return_value=False)):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
                resp = await c.delete("/v1/admin/api-keys/does-not-exist")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    @pytest.mark.parametrize("role", NON_ADMIN_ROLES)
    async def test_non_admin_roles_rejected_403(self, role):
        app = _build_app(role=role)
        with patch("src.routers.admin.crud.revoke_api_key", new=AsyncMock(return_value=True)):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
                resp = await c.delete("/v1/admin/api-keys/k-1")
        assert resp.status_code == 403


class TestListApiKeys:
    @pytest.mark.asyncio
    async def test_admin_sees_serialized_keys(self):
        app = _build_app(role="admin")
        rows = [
            {
                "id": uuid.uuid4(), "name": "svc-key", "scopes": ["query:read"],
                "user_id": uuid.uuid4(),
                "expires_at": datetime.datetime(2027, 1, 1, tzinfo=datetime.timezone.utc),
                "is_revoked": False, "last_used_at": None,
                "created_at": datetime.datetime(2026, 8, 1, tzinfo=datetime.timezone.utc),
            }
        ]
        with patch("src.routers.admin.crud.list_api_keys", new=AsyncMock(return_value=rows)):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
                resp = await c.get("/v1/admin/api-keys")
        assert resp.status_code == 200
        key = resp.json()["api_keys"][0]
        assert isinstance(key["id"], str)
        assert isinstance(key["user_id"], str)
        assert key["last_used_at"] is None
        assert key["created_at"] == "2026-08-01T00:00:00+00:00"

    @pytest.mark.asyncio
    @pytest.mark.parametrize("role", NON_ADMIN_ROLES)
    async def test_non_admin_roles_rejected_403(self, role):
        app = _build_app(role=role)
        with patch("src.routers.admin.crud.list_api_keys", new=AsyncMock(return_value=[])):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
                resp = await c.get("/v1/admin/api-keys")
        assert resp.status_code == 403


class TestGetUsers:
    @pytest.mark.asyncio
    async def test_admin_sees_serialized_users(self):
        app = _build_app(role="admin")
        rows = [
            {
                "id": uuid.uuid4(), "email": "engineer@tenant1.test", "role": "engineer",
                "is_active": True, "last_login": None,
                "created_at": datetime.datetime(2026, 7, 1, tzinfo=datetime.timezone.utc),
            }
        ]
        with patch("src.routers.admin.crud.list_users", new=AsyncMock(return_value=rows)):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
                resp = await c.get("/v1/admin/users")
        assert resp.status_code == 200
        user = resp.json()["users"][0]
        assert isinstance(user["id"], str)
        assert user["email"] == "engineer@tenant1.test"

    @pytest.mark.asyncio
    @pytest.mark.parametrize("role", NON_ADMIN_ROLES)
    async def test_non_admin_roles_rejected_403(self, role):
        app = _build_app(role=role)
        with patch("src.routers.admin.crud.list_users", new=AsyncMock(return_value=[])):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
                resp = await c.get("/v1/admin/users")
        assert resp.status_code == 403


class TestVectorStoreNamespaceHealth:
    """New in Phase 8 (ADR-015). require_min_role("engineer") is a
    genuinely different bar than every other route in this file
    (require_role("admin") exact-match) — admin and engineer pass,
    analyst/auditor/readonly do not."""

    @pytest.mark.asyncio
    async def test_engineer_gets_healthy_status(self):
        app = _build_app(role="engineer", tenant_id="tenant-xyz")
        mock_store = MagicMock()
        mock_store.health_check = AsyncMock(return_value=True)
        with patch("src.routers.admin.get_store", return_value=mock_store) as mocked_get_store:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
                resp = await c.get("/v1/admin/vector-store/namespaces")
        assert resp.status_code == 200
        body = resp.json()
        assert body["tenant_id"] == "tenant-xyz"
        assert body["healthy"] is True
        assert "backend" in body
        mocked_get_store.assert_called_once_with("tenant-xyz")

    @pytest.mark.asyncio
    async def test_admin_also_allowed(self):
        app = _build_app(role="admin")
        mock_store = MagicMock()
        mock_store.health_check = AsyncMock(return_value=True)
        with patch("src.routers.admin.get_store", return_value=mock_store):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
                resp = await c.get("/v1/admin/vector-store/namespaces")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_unhealthy_store_reported_not_raised(self):
        app = _build_app(role="engineer")
        mock_store = MagicMock()
        mock_store.health_check = AsyncMock(return_value=False)
        with patch("src.routers.admin.get_store", return_value=mock_store):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
                resp = await c.get("/v1/admin/vector-store/namespaces")
        assert resp.status_code == 200
        assert resp.json()["healthy"] is False

    @pytest.mark.asyncio
    @pytest.mark.parametrize("role", NON_ENGINEER_OR_ABOVE_ROLES)
    async def test_below_engineer_rejected_403(self, role):
        app = _build_app(role=role)
        mock_store = MagicMock()
        mock_store.health_check = AsyncMock(return_value=True)
        with patch("src.routers.admin.get_store", return_value=mock_store):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
                resp = await c.get("/v1/admin/vector-store/namespaces")
        assert resp.status_code == 403
