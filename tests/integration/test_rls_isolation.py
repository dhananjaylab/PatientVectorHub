"""
RLS tenant-isolation test — closes the Phase 1 risk-register item:
  "PostgreSQL RLS policy silently returns wrong rows for tenant
   isolation" (Critical / HIPAA).

Requires migration 003_enable_rls.py to be applied and the local/cloud
stack's Postgres to be reachable. Run with:
    pytest tests/integration/test_rls_isolation.py -v -m integration

This intentionally does NOT depend on the seeded fixture data from
seed_data.py — it creates and rolls back its own rows inside a single
transaction so it is safe to run repeatedly against a shared database
(including CI's ephemeral Postgres service).

Connection used
----------------
Prefers RLS_TEST_DATABASE_URL if set — this should point at a
NON-superuser, NOBYPASSRLS role with SELECT/INSERT/UPDATE/DELETE on
tenants/users/patients (see .github/workflows/ci.yml's "Create RLS
test role" step). Falls back to DATABASE_URL otherwise.

This matters because the default app role in both local Docker Compose
(POSTGRES_USER=pvh) and CI's ephemeral Postgres service is the initdb
bootstrap superuser, which bypasses RLS unconditionally regardless of
FORCE ROW LEVEL SECURITY. Running this test against that role would
either skip forever (if the bypass check is correct) or produce a
false failure (if it isn't) — neither actually exercises the policy.
RLS_TEST_DATABASE_URL is how CI gets a real, non-bypassing signal.
"""
import os
import uuid
from pathlib import Path

from dotenv import load_dotenv
import pytest

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

pytestmark = pytest.mark.integration

_RAW_URL = (
    os.getenv("RLS_TEST_DATABASE_URL")
    or os.getenv("DATABASE_URL")
    or "postgresql+asyncpg://pvh:pvh_local@localhost:5432/pvh"
)
POSTGRES_URL = _RAW_URL.replace("postgresql+asyncpg://", "postgresql://")

TENANT_A = str(uuid.uuid4())
TENANT_B = str(uuid.uuid4())


async def _make_tenant(conn, tenant_id: str, name: str) -> None:
    await conn.execute(
        "INSERT INTO tenants (id, name, namespace, plan, created_at) "
        "VALUES ($1, $2, $3, 'enterprise', NOW()) "
        "ON CONFLICT (id) DO NOTHING",
        tenant_id, name, f"ns_{tenant_id[:8]}",
    )


async def _make_patient(conn, tenant_id: str) -> str:
    patient_id = str(uuid.uuid4())
    await conn.execute(
        "INSERT INTO patients (id, mrn, tenant_id, is_active, created_at) "
        "VALUES ($1, $2, $3, TRUE, NOW())",
        patient_id, f"vault:v1:TEST_{patient_id[:8]}", tenant_id,
    )
    return patient_id


async def _current_user_bypasses_rls(conn) -> bool:
    """True if the connecting role bypasses RLS entirely.

    Postgres bypasses RLS for a role under TWO independent conditions:
    rolsuper = true, OR rolbypassrls = true — separate pg_roles
    columns, not implied by one another. A role created via
    `CREATE ROLE ... SUPERUSER` gets rolsuper = true but rolbypassrls
    keeps its own default (false) unless explicitly granted.

    Checking only rolbypassrls misses the common case: the Docker
    Compose / CI ephemeral Postgres bootstrap user (POSTGRES_USER=pvh)
    is the initdb bootstrap superuser (rolsuper=true), so a
    rolbypassrls-only check would incorrectly report "does not
    bypass RLS" and let the isolation assertions run — and fail,
    since the superuser sees every row regardless of app.tenant_id.
    """
    return await conn.fetchval(
        "SELECT rolsuper OR rolbypassrls FROM pg_roles WHERE rolname = current_user"
    )


class TestRLSPolicyExists:
    """Sanity checks that the migration actually applied — fail fast
    with a clear message rather than a confusing zero-rows result."""

    @pytest.mark.asyncio
    async def test_rls_enabled_on_patients(self):
        import asyncpg
        conn = await asyncpg.connect(POSTGRES_URL)
        try:
            row = await conn.fetchrow(
                "SELECT relrowsecurity, relforcerowsecurity "
                "FROM pg_class WHERE relname = 'patients'"
            )
            assert row is not None, "patients table not found"
            assert row["relrowsecurity"] is True, (
                "RLS not enabled on patients — run migration 003_enable_rls.py"
            )
            assert row["relforcerowsecurity"] is True, (
                "RLS not FORCED on patients — table owner would bypass "
                "isolation; run migration 003_enable_rls.py"
            )
        finally:
            await conn.close()

    @pytest.mark.asyncio
    async def test_tenant_isolation_policy_exists(self):
        import asyncpg
        conn = await asyncpg.connect(POSTGRES_URL)
        try:
            row = await conn.fetchrow(
                "SELECT polname FROM pg_policy "
                "WHERE polrelid = 'patients'::regclass "
                "AND polname = 'patients_tenant_isolation'"
            )
            assert row is not None, (
                "patients_tenant_isolation policy missing — "
                "run migration 003_enable_rls.py"
            )
        finally:
            await conn.close()


class TestCrossTenantIsolation:
    """The gate the risk register asked for: a cross-tenant query on a
    tenant-scoped table must return exactly zero rows."""

    @pytest.mark.asyncio
    async def test_cross_tenant_query_returns_zero_rows(self):
        import asyncpg
        conn = await asyncpg.connect(POSTGRES_URL)
        try:
            if await _current_user_bypasses_rls(conn):
                pytest.skip(
                    "Current DB role bypasses RLS (superuser or BYPASSRLS); "
                    "cannot assert isolation against this user. Set "
                    "RLS_TEST_DATABASE_URL to a non-superuser, NOBYPASSRLS "
                    "role to get a real signal — see ci.yml's "
                    "'Create RLS test role' step."
                )

            tx = conn.transaction()
            await tx.start()
            try:
                await _make_tenant(conn, TENANT_A, "RLS Test Tenant A")
                await _make_tenant(conn, TENANT_B, "RLS Test Tenant B")
                await _make_patient(conn, TENANT_A)
                await _make_patient(conn, TENANT_A)  # 2 rows for tenant A

                # Scope the session to tenant B and query patients.
                await conn.execute(
                    "SELECT set_config('app.tenant_id', $1, true)", TENANT_B
                )
                count_as_b = await conn.fetchval("SELECT COUNT(*) FROM patients")
                assert count_as_b == 0, (
                    f"RLS isolation FAILED: tenant B saw {count_as_b} rows "
                    "that belong to tenant A"
                )

                # Sanity check the positive path — scoped to the owning
                # tenant, the rows must be visible.
                await conn.execute(
                    "SELECT set_config('app.tenant_id', $1, true)", TENANT_A
                )
                count_as_a = await conn.fetchval("SELECT COUNT(*) FROM patients")
                assert count_as_a == 2, (
                    f"Expected 2 rows visible to owning tenant, got {count_as_a} "
                    "— RLS policy may be over-restrictive"
                )
            finally:
                await tx.rollback()  # never persist test data
        finally:
            await conn.close()

    @pytest.mark.asyncio
    async def test_unscoped_session_sees_zero_rows(self):
        """A connection that never calls SET LOCAL app.tenant_id must
        fail closed, not fail open."""
        import asyncpg
        conn = await asyncpg.connect(POSTGRES_URL)
        try:
            if await _current_user_bypasses_rls(conn):
                pytest.skip(
                    "Current DB role bypasses RLS (superuser or BYPASSRLS); "
                    "cannot assert fail-closed behavior against this user. "
                    "Set RLS_TEST_DATABASE_URL — see ci.yml."
                )

            tx = conn.transaction()
            await tx.start()
            try:
                await _make_tenant(conn, TENANT_A, "RLS Test Tenant A")
                await _make_patient(conn, TENANT_A)

                # No SET LOCAL app.tenant_id at all this time.
                count = await conn.fetchval("SELECT COUNT(*) FROM patients")
                assert count == 0, (
                    "Unscoped session saw rows without setting app.tenant_id "
                    "— RLS is fail-open, not fail-closed"
                )
            finally:
                await tx.rollback()
        finally:
            await conn.close()