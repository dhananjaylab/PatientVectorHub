"""
api-gateway/tests/integration/test_bola_adversarial.py — Phase 11 /
ADR-018 Stage 11.4.

OWASP API1:2023 (Broken Object Level Authorization)-scoped, and the
piece of the original "RLS pen test" roadmap line that genuinely
belongs in tests/integration/, not tests/security/: unlike this
phase's JWT and function-level-authorization adversarial tests (both
fully unit-testable with a mocked DB), a real BOLA check needs actual
cross-tenant rows under real RLS enforcement -- exactly what
test_rls_isolation.py and test_rls_isolation_core_tables.py already
verify at the raw-SQL/session level. This file extends that same
verified mechanism up to the actual HTTP layer: does a real request
through the real router, with the real (non-overridden) get_db
dependency, correctly turn "tenant A's token, tenant B's job ID" into
a 404 -- not tenant B's data?

crud.get_ingestion_job()'s own query has no tenant_id in its WHERE
clause at all (`SELECT ... FROM ingestion_jobs WHERE id = :jid`) --
confirmed by reading it directly. Every bit of tenant isolation for
this specific route comes from RLS alone. That makes this the single
highest-value BOLA test for this architecture: if RLS's app.tenant_id
session variable were ever misconfigured, this exact query is what
would silently start returning the wrong tenant's data, and no
application-level check would catch it.

VERIFICATION STATUS: written and reviewed against the real schema and
route code, but NOT executed in the sandbox this phase's other tests
ran in -- no live Postgres was available there (same environment
constraint test_rls_isolation.py's own suite has always had; this
file is meant to run alongside it, under the same
RLS_TEST_DATABASE_URL). Run for real before relying on it:
    pytest tests/integration/test_bola_adversarial.py -v -m integration
"""
import os
import uuid
from pathlib import Path

import pytest
from dotenv import load_dotenv
from httpx import ASGITransport, AsyncClient

load_dotenv(Path(__file__).resolve().parents[3] / ".env")

pytestmark = pytest.mark.integration

skip_integration = pytest.mark.skipif(
    os.getenv("SKIP_INTEGRATION_TESTS", "").lower() in ("true", "1", "yes"),
    reason="Integration tests skipped (SKIP_INTEGRATION_TESTS=true)",
)

_RAW_URL = (
    os.getenv("RLS_TEST_DATABASE_URL")
    or os.getenv("DATABASE_URL")
    or "postgresql+asyncpg://pvh:pvh_local@localhost:5432/pvh"
)
POSTGRES_URL = _RAW_URL.replace("postgresql+asyncpg://", "postgresql://")

TENANT_A = str(uuid.uuid4())
TENANT_B = str(uuid.uuid4())


async def _seed_tenant_with_job(conn, tenant_id: str, tenant_name: str) -> str:
    await conn.execute(
        "INSERT INTO tenants (id, name, namespace, plan, created_at) "
        "VALUES ($1, $2, $3, 'enterprise', NOW()) ON CONFLICT (id) DO NOTHING",
        tenant_id, tenant_name, f"ns_{tenant_id[:8]}",
    )
    job_id = str(uuid.uuid4())
    await conn.execute(
        "INSERT INTO ingestion_jobs "
        "(id, name, status, source_type, tenant_id, created_at) "
        "VALUES ($1, $2, 'completed', 'api_push', $3, NOW())",
        job_id, f"bola-test-job-{tenant_id[:8]}", tenant_id,
    )
    return job_id


def _build_app_with_real_db(role: str, tenant_id: str):
    """Deliberately does NOT override get_db, unlike every unit-test
    harness elsewhere in this suite -- the real dependency is exactly
    what sets app.tenant_id via SET LOCAL for RLS to act on. Mocking
    it here would test nothing."""
    from fastapi import FastAPI
    from starlette.middleware.base import BaseHTTPMiddleware

    from src.errors import PVHError, pvh_exception_handler
    from src.routers.ingest import router

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
    app.include_router(router, prefix="/v1/ingest")
    return app


class TestBOLACrossTenantJobAccess:
    @pytest.mark.asyncio
    @skip_integration
    async def test_tenant_a_cannot_read_tenant_bs_job_by_id(self):
        import asyncpg

        conn = await asyncpg.connect(POSTGRES_URL)
        try:
            row = await conn.fetchval(
                "SELECT rolsuper OR rolbypassrls FROM pg_roles WHERE rolname = current_user"
            )
            if row:
                pytest.skip(
                    "connecting role bypasses RLS -- set RLS_TEST_DATABASE_URL "
                    "to a non-superuser, NOBYPASSRLS role (see this repo's "
                    "'Create RLS test role' CI step)"
                )

            await _seed_tenant_with_job(conn, TENANT_A, "BOLA Test Tenant A")
            tenant_b_job_id = await _seed_tenant_with_job(conn, TENANT_B, "BOLA Test Tenant B")

            app = _build_app_with_real_db(role="engineer", tenant_id=TENANT_A)
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://t"
            ) as c:
                resp = await c.get(f"/v1/ingest/jobs/{tenant_b_job_id}")

            # The correct, secure answer is 404 -- indistinguishable
            # from a genuinely nonexistent ID, per crud.get_ingestion_job's
            # own no-tenant-filter query relying entirely on RLS. A 200
            # here means RLS silently failed and tenant A can read
            # tenant B's ingestion job metadata.
            assert resp.status_code == 404, (
                f"BOLA: tenant A read tenant B's job via RLS bypass -- "
                f"got {resp.status_code}, expected 404. Response: {resp.text}"
            )
        finally:
            await conn.execute("DELETE FROM ingestion_jobs WHERE tenant_id IN ($1, $2)",
                                TENANT_A, TENANT_B)
            await conn.execute("DELETE FROM tenants WHERE id IN ($1, $2)", TENANT_A, TENANT_B)
            await conn.close()

    @pytest.mark.asyncio
    @skip_integration
    async def test_tenant_a_can_read_its_own_job(self):
        """Negative-of-the-negative control, same reasoning as the
        function-level-authorization suite's own: proves RLS isn't
        just blocking everything (which would make the 404 above
        meaningless), by confirming tenant A can still read its own
        job through the identical code path."""
        import asyncpg

        conn = await asyncpg.connect(POSTGRES_URL)
        try:
            row = await conn.fetchval(
                "SELECT rolsuper OR rolbypassrls FROM pg_roles WHERE rolname = current_user"
            )
            if row:
                pytest.skip("connecting role bypasses RLS")

            tenant_a_job_id = await _seed_tenant_with_job(conn, TENANT_A, "BOLA Test Tenant A")

            app = _build_app_with_real_db(role="engineer", tenant_id=TENANT_A)
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://t"
            ) as c:
                resp = await c.get(f"/v1/ingest/jobs/{tenant_a_job_id}")

            assert resp.status_code == 200
            assert resp.json()["job_id"] == tenant_a_job_id
        finally:
            await conn.execute("DELETE FROM ingestion_jobs WHERE tenant_id = $1", TENANT_A)
            await conn.execute("DELETE FROM tenants WHERE id = $1", TENANT_A)
            await conn.close()
