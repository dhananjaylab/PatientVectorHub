"""Unit tests for api-gateway/src/middleware/auth.py."""
import sys
import os
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "api-gateway"))

from src.middleware.auth import KeycloakJWTMiddleware  # noqa: E402


class TestExtractRole:
    def test_picks_highest_priority_role_when_multiple_present(self):
        payload = {"realm_access": {"roles": ["auditor", "engineer", "readonly"]}}
        assert KeycloakJWTMiddleware._extract_role(payload) == "engineer"

    def test_admin_outranks_everything(self):
        payload = {"realm_access": {"roles": ["readonly", "admin", "analyst"]}}
        assert KeycloakJWTMiddleware._extract_role(payload) == "admin"

    def test_no_recognized_roles_defaults_to_readonly(self):
        payload = {"realm_access": {"roles": ["some-unrelated-realm-role"]}}
        assert KeycloakJWTMiddleware._extract_role(payload) == "readonly"

    def test_missing_realm_access_defaults_to_readonly(self):
        assert KeycloakJWTMiddleware._extract_role({}) == "readonly"


class TestRoleFromScopes:
    def test_admin_write_maps_to_admin(self):
        assert KeycloakJWTMiddleware._role_from_scopes(["admin:write"]) == "admin"

    def test_ingest_write_maps_to_engineer(self):
        assert KeycloakJWTMiddleware._role_from_scopes(["ingest:write"]) == "engineer"

    def test_query_read_maps_to_analyst(self):
        assert KeycloakJWTMiddleware._role_from_scopes(["query:read"]) == "analyst"

    def test_audit_read_maps_to_auditor(self):
        assert KeycloakJWTMiddleware._role_from_scopes(["audit:read"]) == "auditor"

    def test_highest_privilege_scope_wins_when_multiple_present(self):
        assert (
            KeycloakJWTMiddleware._role_from_scopes(["query:read", "admin:write"]) == "admin"
        )

    def test_unrecognized_scopes_default_to_readonly(self):
        assert KeycloakJWTMiddleware._role_from_scopes(["something:else"]) == "readonly"

    def test_empty_scopes_default_to_readonly(self):
        assert KeycloakJWTMiddleware._role_from_scopes([]) == "readonly"


class TestMiddlewareRequestHandling:
    """Request-level checks against a minimal app — verifies public paths,
    anonymous pass-through, and malformed-token rejection without needing a
    live Keycloak or Postgres (those are exercised via manual verification
    against a real Postgres instance + PyJWKClient during development; see
    the chat summary for what was checked live)."""

    @pytest.fixture
    def app(self):
        from fastapi import FastAPI
        from starlette.requests import Request

        app = FastAPI()

        @app.get("/health")
        async def health():
            return {"status": "alive"}

        @app.get("/whoami")
        async def whoami(request: Request):
            return {
                "role": getattr(request.state, "role", None),
                "auth_method": getattr(request.state, "auth_method", None),
            }

        app.add_middleware(
            KeycloakJWTMiddleware,
            jwks_url="http://keycloak.invalid/realms/patientvectorhub/protocol/openid-connect/certs",
            public_paths=frozenset({"/health"}),
        )
        return app

    @pytest.mark.asyncio
    async def test_public_path_bypasses_middleware_entirely(self, app):
        from httpx import AsyncClient, ASGITransport

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
            resp = await c.get("/health")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_no_credentials_passes_through_anonymous(self, app):
        from httpx import AsyncClient, ASGITransport

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
            resp = await c.get("/whoami")
        assert resp.status_code == 200
        assert resp.json() == {"role": None, "auth_method": None}

    @pytest.mark.asyncio
    async def test_malformed_bearer_token_returns_401_not_a_crash(self, app):
        from httpx import AsyncClient, ASGITransport

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
            resp = await c.get("/whoami", headers={"Authorization": "Bearer not-a-real-jwt"})
        assert resp.status_code == 401
        assert resp.json()["error"]["code"] == "AUTHENTICATION_FAILED"

    @pytest.mark.asyncio
    async def test_api_key_resolution_failure_returns_503_not_a_crash(self, app, monkeypatch):
        from httpx import AsyncClient, ASGITransport
        from unittest.mock import AsyncMock
        import src.db.crud as crud_module

        # Deterministic regardless of whether a real Postgres happens to be
        # reachable from wherever this test runs — resolve_api_key raising
        # (DB unreachable, resolver function missing, etc.) must become a
        # 503, never propagate a raw exception past the ASGI boundary.
        monkeypatch.setattr(
            crud_module, "resolve_api_key", AsyncMock(side_effect=RuntimeError("boom"))
        )
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
            resp = await c.get("/whoami", headers={"X-API-Key": "pvh_some_fake_key"})
        assert resp.status_code == 503
        assert resp.json()["error"]["code"] == "AUTHENTICATION_UNAVAILABLE"

    @pytest.mark.asyncio
    async def test_api_key_not_found_returns_401_not_a_crash(self, app, monkeypatch):
        from httpx import AsyncClient, ASGITransport
        from unittest.mock import AsyncMock
        import src.db.crud as crud_module

        # Covers: key genuinely doesn't exist, revoked, expired, AND the
        # ADR-010 "BYPASSRLS not yet granted in this environment" case —
        # all collapse to the same None return from resolve_api_key(),
        # and must all produce the same generic 401 here.
        monkeypatch.setattr(crud_module, "resolve_api_key", AsyncMock(return_value=None))
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
            resp = await c.get("/whoami", headers={"X-API-Key": "pvh_some_fake_key"})
        assert resp.status_code == 401
        assert resp.json()["error"]["code"] == "AUTHENTICATION_FAILED"

    @pytest.mark.asyncio
    async def test_api_key_resolved_populates_request_state(self, app, monkeypatch):
        from httpx import AsyncClient, ASGITransport
        from unittest.mock import AsyncMock
        import src.db.crud as crud_module

        monkeypatch.setattr(
            crud_module,
            "resolve_api_key",
            AsyncMock(
                return_value={
                    "key_id": "k-1",
                    "tenant_id": "t-1",
                    "user_id": "u-1",
                    "scopes": ["ingest:write"],
                    "is_revoked": False,
                    "expires_at": None,
                }
            ),
        )
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
            resp = await c.get("/whoami", headers={"X-API-Key": "pvh_a_real_looking_key"})
        assert resp.status_code == 200
        assert resp.json() == {"role": "engineer", "auth_method": "api_key"}
