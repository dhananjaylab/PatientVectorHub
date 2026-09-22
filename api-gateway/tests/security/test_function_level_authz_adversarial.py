"""
api-gateway/tests/security/test_function_level_authz_adversarial.py —
Phase 11 / ADR-018 Stage 11.4.

OWASP API5:2023 (Broken Function-Level Authorization)-scoped. This is
a genuinely different question from tests/unit/test_rbac.py's own
coverage: that file proves require_role()/require_min_role()'s
*internal logic* is correct in isolation (given role X, is X >= Y?).
This file proves those guards are actually *wired onto* the real
routers -- the kind of gap that shows up when someone adds a new route
and forgets the decorator, not when the guard's own comparison logic
has a bug. Reuses the exact standalone-app + fake-auth-middleware
harness tests/unit/test_admin_router.py already established (a fake
middleware populating request.state directly, matching what
middleware.rbac's guards actually read -- not a JWT round-trip, which
test_jwt_adversarial.py in this same directory already covers).

Every case below drives the request from the lowest role that should
be refused (readonly, or one step below the actual requirement) at the
real mounted router, not from a synthetic test double for that router.
"""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from starlette.middleware.base import BaseHTTPMiddleware


def _build_app(router, prefix: str, role: str, tenant_id: str = "tenant-a"):
    from src.deps import get_db
    from src.errors import PVHError, pvh_exception_handler

    app = FastAPI()
    app.add_exception_handler(PVHError, pvh_exception_handler)  # type: ignore

    class _FakeAuthMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request, call_next):
            request.state.user_id = "attacker"
            request.state.tenant_id = tenant_id
            request.state.role = role
            request.state.email = None
            request.state.auth_method = "jwt"
            request.state.api_key_id = None
            request.state.scopes = []
            return await call_next(request)

    app.add_middleware(_FakeAuthMiddleware)
    app.include_router(router, prefix=prefix)

    async def _fake_get_db():
        yield AsyncMock()

    app.dependency_overrides[get_db] = _fake_get_db
    return app


async def _request(app, method: str, path: str, **kwargs):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        return await c.request(method, path, **kwargs)


class TestFunctionLevelAuthorizationBypass:
    """Each case: the lowest role one step below the route's actual
    requirement, hitting the real route, expecting a hard 403 -- not a
    200, not a 500 that happens to also block it for the wrong reason.
    """

    @pytest.mark.asyncio
    async def test_readonly_cannot_create_ingest_job(self):
        from src.routers.ingest import router

        app = _build_app(router, "/v1/ingest", role="readonly")
        resp = await _request(
            app, "POST", "/v1/ingest/jobs",
            json={"name": "x", "source_type": "api_push",
                  "documents": [{"source_path": "r2://x", "document_type": "lab_result",
                                  "patient_id": "p1"}]},
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_readonly_cannot_list_admin_users(self):
        from src.routers.admin import router

        app = _build_app(router, "/v1/admin", role="readonly")
        resp = await _request(app, "GET", "/v1/admin/users")
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_engineer_cannot_list_admin_users(self):
        """One step below is the real test -- engineer (role 3) is
        closer to admin (role 4) than readonly is, and a hierarchy
        off-by-one bug is more likely to surface at the boundary than
        at the extreme."""
        from src.routers.admin import router

        app = _build_app(router, "/v1/admin", role="engineer")
        resp = await _request(app, "GET", "/v1/admin/users")
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_analyst_cannot_export_audit_logs(self):
        """export_audit_logs specifically -- a different, stricter
        requirement (auditor+) than the plain GET /v1/audit/logs list
        route (also auditor+, but exporting is the more sensitive of
        the two and worth its own explicit case)."""
        from src.routers.audit import router

        app = _build_app(router, "/v1/audit", role="analyst")
        resp = await _request(app, "GET", "/v1/audit/logs/export")
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_readonly_cannot_read_audit_logs(self):
        from src.routers.audit import router

        app = _build_app(router, "/v1/audit", role="readonly")
        resp = await _request(app, "GET", "/v1/audit/logs")
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_readonly_cannot_run_query(self):
        """Verified against the real route requirement before writing
        this (require_min_role("analyst") in query.py) rather than
        assumed -- an earlier draft of this test incorrectly assumed
        readonly could reach this route and asserted the opposite of
        what's below."""
        from src.routers.query import router

        app = _build_app(router, "/v1/query", role="readonly")
        resp = await _request(
            app, "POST", "/v1/query", json={"query_text": "test", "top_k": 5}
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_analyst_is_not_blocked_at_the_authorization_layer(self):
        """Negative-of-the-negative control: analyst is query.py's
        actual floor (require_min_role("analyst")) -- this confirms
        the harness itself isn't just refusing every request by
        default, which would make every 403 above meaningless."""
        from src.routers.query import router

        app = _build_app(router, "/v1/query", role="analyst")
        resp = await _request(
            app, "POST", "/v1/query", json={"query_text": "test", "top_k": 5}
        )
        # Not asserting 200 -- that needs a real retriever/DB, out of
        # scope for this harness (AsyncMock stands in for get_db, not
        # the retrieval pipeline). Asserting it does NOT fail with 403
        # is the actual claim: analyst is not blocked at the
        # authorization layer for this route.
        assert resp.status_code != 403
