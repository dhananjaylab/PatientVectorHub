"""
Unit tests for api-gateway/src/middleware/rate_limit.py (Phase 8 /
ADR-015).

TestRateLimitKey exercises rate_limit_key()'s pure logic against faked
request.state, using this codebase's established MagicMock(spec=[...])
idiom (see tests/unit/test_rbac.py's _fake_request()) so getattr(...,
default) correctly falls through for attributes that were never set,
rather than returning a truthy MagicMock stand-in.

TestRateLimitEnforcement builds a small standalone app (own toy route,
never reused by any real router) and deliberately re-enables the shared
`limiter` singleton around just that test — the autouse
_disable_rate_limiting fixture in tests/conftest.py disables it process-
wide for every other test in this suite; see that fixture's docstring
for why. Verifies the actual 429 + this codebase's standard error
envelope end to end, not just the key-derivation logic in isolation.

IMPORTANT (verified against the installed library's actual source, not
assumed): slowapi/`limits` scopes each `@limiter.limit(...)` bucket by
`f"{view_func.__module__}.{view_func.__name__}"` — the decorated
function's bare `__name__` plus its module, NOT the route path and NOT
the function's full `__qualname__`. Reproduced concretely: two toy
routes in two different test functions, decorated at different times,
both named `toy`, silently shared ONE rate-limit bucket even though
they lived on entirely separate FastAPI app instances with different
paths and different configured limits — the second route inherited the
first's already-exhausted "2/minute" count instead of enforcing its own
"1000/minute". Giving each toy route in this file a distinct function
name (never `toy` twice) is not just tidiness, it's required for test
isolation. The same rule matters for the real routers too: every route
handler in this codebase already has a distinct name within its module
(ingest.py: create_job/get_job/list_jobs; query.py: rag_query; admin.py:
create_key/revoke_key/list_keys/get_users/get_namespaces; audit.py:
get_audit_logs/export_audit_logs) — no two rate-limited routes anywhere
in this app share a bare function name within the same module, so this
gotcha does not affect production behavior, only careless test-route
naming. Don't reuse a route handler's function name elsewhere in the
same module if it's ever decorated with @limiter.limit(...).
"""

from unittest.mock import MagicMock

import pytest


def _fake_request(*, api_key_id=None, tenant_id=None, user_id=None, remote_ip="203.0.113.5"):
    """Mirrors test_rbac.py's _fake_request() pattern: MagicMock(spec=[...])
    so request.state only has the attributes explicitly given — anything
    else correctly falls through getattr(..., default) instead of
    returning a truthy MagicMock stand-in."""
    request = MagicMock()
    state_attrs = {}
    if api_key_id is not None:
        state_attrs["api_key_id"] = api_key_id
    if tenant_id is not None:
        state_attrs["tenant_id"] = tenant_id
    if user_id is not None:
        state_attrs["user_id"] = user_id
    request.state = MagicMock(spec=list(state_attrs.keys()))
    for key, value in state_attrs.items():
        setattr(request.state, key, value)
    request.client.host = remote_ip
    return request


class TestRateLimitKey:
    def test_api_key_id_takes_priority_over_tenant_and_user(self):
        from src.middleware.rate_limit import rate_limit_key

        request = _fake_request(api_key_id="key-1", tenant_id="t-1", user_id="u-1")
        assert rate_limit_key(request) == "apikey:key-1"

    def test_tenant_and_user_used_when_no_api_key(self):
        from src.middleware.rate_limit import rate_limit_key

        request = _fake_request(tenant_id="t-1", user_id="u-1")
        assert rate_limit_key(request) == "user:t-1:u-1"

    def test_falls_back_to_remote_address_with_no_auth_context(self):
        """AUTH_ENABLED=false (local dev default) — no auth middleware
        populated request.state at all."""
        from src.middleware.rate_limit import rate_limit_key

        request = _fake_request(remote_ip="203.0.113.5")
        assert rate_limit_key(request) == "ip:203.0.113.5"

    def test_falls_back_to_ip_when_only_tenant_id_present(self):
        """Defensive: tenant_id without user_id (shouldn't happen given
        how KeycloakJWTMiddleware populates both together, but the key
        function must not raise or silently key on a partial identity)."""
        from src.middleware.rate_limit import rate_limit_key

        request = _fake_request(tenant_id="t-1")
        assert rate_limit_key(request).startswith("ip:")

    def test_different_tenants_produce_different_keys(self):
        """The whole point of not keying on raw IP — two tenants behind
        the same NAT/proxy must not share one bucket."""
        from src.middleware.rate_limit import rate_limit_key

        a = _fake_request(tenant_id="tenant-a", user_id="user-1", remote_ip="203.0.113.5")
        b = _fake_request(tenant_id="tenant-b", user_id="user-1", remote_ip="203.0.113.5")
        assert rate_limit_key(a) != rate_limit_key(b)


class TestRateLimitEnforcement:
    def test_exceeding_limit_returns_429_with_standard_envelope(self):
        from fastapi import FastAPI, Request, Response
        from fastapi.testclient import TestClient
        from slowapi.errors import RateLimitExceeded

        from src.middleware.rate_limit import limiter, rate_limit_exceeded_handler

        app = FastAPI()
        app.state.limiter = limiter
        app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)  # type: ignore

        @app.get("/__test_only_toy_route__")
        @limiter.limit("2/minute")
        async def toy_exceeding_limit_route(request: Request, response: Response):
            return {"ok": True}

        original_enabled = limiter.enabled
        limiter.enabled = True
        try:
            client = TestClient(app)
            statuses = [client.get("/__test_only_toy_route__").status_code for _ in range(2)]
            assert statuses == [200, 200]

            final = client.get("/__test_only_toy_route__")
            assert final.status_code == 429
            body = final.json()
            assert body["error"]["code"] == "RATE_LIMIT_EXCEEDED"
            assert "Rate limit exceeded" in body["error"]["message"]
            assert isinstance(body["error"]["retry_after_seconds"], int)
            assert body["error"]["retry_after_seconds"] > 0
            assert final.headers.get("retry-after") is not None
        finally:
            limiter.enabled = original_enabled

    def test_below_limit_never_429s(self):
        from fastapi import FastAPI, Request, Response
        from fastapi.testclient import TestClient
        from slowapi.errors import RateLimitExceeded

        from src.middleware.rate_limit import limiter, rate_limit_exceeded_handler

        app = FastAPI()
        app.state.limiter = limiter
        app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)  # type: ignore

        @app.get("/__test_only_toy_route_generous__")
        @limiter.limit("1000/minute")
        async def toy_below_limit_route(request: Request, response: Response):
            return {"ok": True}

        original_enabled = limiter.enabled
        limiter.enabled = True
        try:
            client = TestClient(app)
            for _ in range(5):
                assert client.get("/__test_only_toy_route_generous__").status_code == 200
        finally:
            limiter.enabled = original_enabled

    def test_disabled_limiter_never_429s_regardless_of_call_count(self):
        from fastapi import FastAPI, Request, Response
        from fastapi.testclient import TestClient
        from slowapi.errors import RateLimitExceeded

        from src.middleware.rate_limit import limiter, rate_limit_exceeded_handler

        app = FastAPI()
        app.state.limiter = limiter
        app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)  # type: ignore

        @app.get("/__test_only_toy_route_disabled__")
        @limiter.limit("1/minute")
        async def toy_disabled_route(request: Request, response: Response):
            return {"ok": True}

        # Deliberately left at whatever the autouse fixture set (False) —
        # this test exists specifically to prove the disabled state, so
        # it does NOT flip enabled=True here.
        assert limiter.enabled is False
        client = TestClient(app)
        for _ in range(4):
            assert client.get("/__test_only_toy_route_disabled__").status_code == 200


class TestLimiterConfiguration:
    def test_limiter_reuses_shared_redis_url_not_a_second_setting(self):
        from src.config import settings
        from src.middleware.rate_limit import limiter

        assert limiter._storage_uri == settings.REDIS_URL

    def test_limiter_has_in_memory_fallback_enabled(self):
        """Graceful degradation if Redis is briefly unreachable — falls
        back to per-instance in-memory counting rather than either
        blocking all traffic or disabling enforcement outright."""
        from src.middleware.rate_limit import limiter

        assert limiter._in_memory_fallback_enabled is True

    def test_limiter_swallows_backend_errors(self):
        """Fail-open on the limiter's own backend trouble — mirrors the
        original design docs' Kong rate-limit config's own
        `fault_tolerant: true`. Deliberately the opposite posture from
        this codebase's RLS/API-key fail-closed guarantees (ADR-010):
        rate limiting protects availability, it doesn't gate access."""
        from src.middleware.rate_limit import limiter

        assert limiter._swallow_errors is True
