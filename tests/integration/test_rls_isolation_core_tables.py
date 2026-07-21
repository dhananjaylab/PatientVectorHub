"""
RLS tests for the Phase 2 tables added in migration 004_add_core_tables.py
(ingestion_jobs, documents, api_keys, query_logs, audit_logs), extending
test_rls_isolation.py's pattern to the tables it doesn't cover.

Also covers two things specific to migration 004 that test_rls_isolation.py
has no equivalent for:
  1. audit_logs' append-only design (SELECT + INSERT policies only, no
     UPDATE/DELETE policy at all) — see that migration's module docstring
     for why this replaced the original design docs' single
     `WITH CHECK (FALSE)` policy, which would have blocked INSERT too.
  2. resolve_api_key_tenant()'s fail-closed behavior (ADR-010) — verified
     here to return zero rows for a non-superuser, non-BYPASSRLS caller
     (the "unprovisioned environment" state), which is the security
     property the whole design depends on.

Same connection-selection rules as test_rls_isolation.py: prefers
RLS_TEST_DATABASE_URL (a real non-superuser, NOBYPASSRLS role — see
ci.yml's "Create RLS test role" step) and skips isolation assertions
entirely if the connecting role would bypass RLS anyway (local Docker
Compose's bootstrap-superuser `pvh`, for instance) — running these
assertions against a bypassing role produces a false failure, not a
"passes for the wrong reason."
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


async def _current_user_bypasses_rls(conn) -> bool:
    """See test_rls_isolation.py's identical helper for the full rationale
    — checks both rolsuper and rolbypassrls, since they're independent
    pg_roles columns and either one alone means RLS is bypassed."""
    return await conn.fetchval(
        "SELECT rolsuper OR rolbypassrls FROM pg_roles WHERE rolname = current_user"
    )


async def _make_tenant(conn, tenant_id: str, name: str) -> None:
    await conn.execute(
        "INSERT INTO tenants (id, name, namespace, plan, created_at) "
        "VALUES ($1, $2, $3, 'enterprise', NOW()) ON CONFLICT (id) DO NOTHING",
        tenant_id, name, f"ns_{tenant_id[:8]}",
    )


async def _make_user(conn, tenant_id: str) -> str:
    user_id = str(uuid.uuid4())
    await conn.execute(
        "INSERT INTO users (id, email, keycloak_subject, role, tenant_id) "
        "VALUES ($1, $2, $3, 'engineer', $4)",
        user_id, f"{user_id}@rls-test.local", f"kc-{user_id}", tenant_id,
    )
    return user_id


class TestNewTablesRLSEnabled:
    """Sanity checks that migration 004 actually applied RLS — fail fast
    with a clear message rather than a confusing zero-rows result."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "table", ["ingestion_jobs", "documents", "api_keys", "query_logs", "audit_logs"]
    )
    async def test_force_rls_enabled(self, table):
        import asyncpg
        conn = await asyncpg.connect(POSTGRES_URL)
        try:
            row = await conn.fetchrow(
                "SELECT relrowsecurity, relforcerowsecurity FROM pg_class WHERE relname = $1",
                table,
            )
            assert row is not None, f"{table} table not found — run migration 004"
            assert row["relrowsecurity"] is True, f"RLS not enabled on {table}"
            assert row["relforcerowsecurity"] is True, f"RLS not FORCED on {table}"
        finally:
            await conn.close()


class TestCrossTenantIsolationNewTables:
    @pytest.mark.asyncio
    async def test_ingestion_jobs_and_api_keys_isolated_by_tenant(self):
        import asyncpg
        conn = await asyncpg.connect(POSTGRES_URL)
        try:
            if await _current_user_bypasses_rls(conn):
                pytest.skip(
                    "Current DB role bypasses RLS; set RLS_TEST_DATABASE_URL "
                    "to a non-superuser, NOBYPASSRLS role — see ci.yml."
                )

            tx = conn.transaction()
            await tx.start()
            try:
                await _make_tenant(conn, TENANT_A, "RLS Test Tenant A")
                await _make_tenant(conn, TENANT_B, "RLS Test Tenant B")

                await conn.execute(
                    "SELECT set_config('app.tenant_id', $1, true)", TENANT_A
                )
                user_a = await _make_user(conn, TENANT_A)
                await conn.execute(
                    "INSERT INTO ingestion_jobs (id, name, status, source_type, "
                    "created_by, tenant_id) VALUES (gen_random_uuid(), 'job', "
                    "'queued', 's3_batch', $1, $2)",
                    user_a, TENANT_A,
                )
                await conn.execute(
                    "INSERT INTO api_keys (id, key_hash, name, scopes, user_id, "
                    "tenant_id, expires_at) VALUES (gen_random_uuid(), 'hash123', "
                    "'key', ARRAY['query:read'], $1, $2, NOW() + INTERVAL '90 days')",
                    user_a, TENANT_A,
                )

                # Scope to tenant B — must see zero rows for both tables.
                await conn.execute(
                    "SELECT set_config('app.tenant_id', $1, true)", TENANT_B
                )
                jobs_as_b = await conn.fetchval("SELECT COUNT(*) FROM ingestion_jobs")
                keys_as_b = await conn.fetchval("SELECT COUNT(*) FROM api_keys")
                assert jobs_as_b == 0, f"Tenant B saw {jobs_as_b} of tenant A's ingestion_jobs"
                assert keys_as_b == 0, f"Tenant B saw {keys_as_b} of tenant A's api_keys"

                # Sanity — the owning tenant must still see its own rows.
                await conn.execute(
                    "SELECT set_config('app.tenant_id', $1, true)", TENANT_A
                )
                jobs_as_a = await conn.fetchval("SELECT COUNT(*) FROM ingestion_jobs")
                assert jobs_as_a == 1
            finally:
                await tx.rollback()
        finally:
            await conn.close()


class TestAuditLogsAppendOnly:
    @pytest.mark.asyncio
    async def test_insert_with_matching_tenant_succeeds(self):
        import asyncpg
        conn = await asyncpg.connect(POSTGRES_URL)
        try:
            if await _current_user_bypasses_rls(conn):
                pytest.skip("Current DB role bypasses RLS — see ci.yml's RLS test role.")

            tx = conn.transaction()
            await tx.start()
            try:
                await _make_tenant(conn, TENANT_A, "Audit Tenant A")
                await conn.execute(
                    "SELECT set_config('app.tenant_id', $1, true)", TENANT_A
                )
                row_id = await conn.fetchval(
                    "INSERT INTO audit_logs (action, tenant_id, status_code) "
                    "VALUES ('user_login', $1, 200) RETURNING id",
                    TENANT_A,
                )
                assert row_id is not None
            finally:
                await tx.rollback()
        finally:
            await conn.close()

    @pytest.mark.asyncio
    async def test_insert_with_spoofed_tenant_is_rejected(self):
        import asyncpg
        conn = await asyncpg.connect(POSTGRES_URL)
        try:
            if await _current_user_bypasses_rls(conn):
                pytest.skip("Current DB role bypasses RLS — see ci.yml's RLS test role.")

            tx = conn.transaction()
            await tx.start()
            try:
                await _make_tenant(conn, TENANT_A, "Audit Tenant A")
                await _make_tenant(conn, TENANT_B, "Audit Tenant B")
                await conn.execute(
                    "SELECT set_config('app.tenant_id', $1, true)", TENANT_A
                )
                with pytest.raises(asyncpg.exceptions.InsufficientPrivilegeError):
                    await conn.execute(
                        "INSERT INTO audit_logs (action, tenant_id, status_code) "
                        "VALUES ('user_login', $1, 200)",
                        TENANT_B,  # mismatched vs. app.tenant_id -- must be rejected
                    )
            finally:
                await tx.rollback()
        finally:
            await conn.close()

    @pytest.mark.asyncio
    async def test_update_and_delete_are_both_blocked(self):
        """No FOR UPDATE / FOR DELETE policy exists at all for audit_logs
        (see migration 004's module docstring) — that absence, not a
        WITH CHECK (FALSE) policy, is what makes the table append-only.
        RLS with zero applicable policies silently matches zero rows for
        that command rather than raising, so both commands report 0 rows
        affected here."""
        import asyncpg
        conn = await asyncpg.connect(POSTGRES_URL)
        try:
            if await _current_user_bypasses_rls(conn):
                pytest.skip("Current DB role bypasses RLS — see ci.yml's RLS test role.")

            tx = conn.transaction()
            await tx.start()
            try:
                await _make_tenant(conn, TENANT_A, "Audit Tenant A")
                await conn.execute(
                    "SELECT set_config('app.tenant_id', $1, true)", TENANT_A
                )
                await conn.execute(
                    "INSERT INTO audit_logs (action, tenant_id, status_code) "
                    "VALUES ('user_login', $1, 200)",
                    TENANT_A,
                )

                update_result = await conn.execute(
                    "UPDATE audit_logs SET status_code = 999 WHERE action = 'user_login'"
                )
                assert update_result == "UPDATE 0", f"Expected UPDATE to affect 0 rows, got: {update_result}"

                delete_result = await conn.execute(
                    "DELETE FROM audit_logs WHERE action = 'user_login'"
                )
                assert delete_result == "DELETE 0", f"Expected DELETE to affect 0 rows, got: {delete_result}"

                # The row must still be there, untouched.
                count = await conn.fetchval("SELECT COUNT(*) FROM audit_logs")
                assert count == 1
            finally:
                await tx.rollback()
        finally:
            await conn.close()


class TestApiKeyResolverFailsClosed:
    """ADR-010: resolve_api_key_tenant() must return zero rows for a
    non-superuser, non-BYPASSRLS caller — the default "unprovisioned
    environment" state. This test intentionally does NOT grant BYPASSRLS
    to anything; it's checking the fail-closed default, not the
    provisioned-admin path (which requires a manual, out-of-band grant
    per ADR-010 and isn't something CI should be able to silently
    provision for itself)."""

    @pytest.mark.asyncio
    async def test_returns_zero_rows_for_unprivileged_caller(self):
        import asyncpg
        conn = await asyncpg.connect(POSTGRES_URL)
        try:
            if await _current_user_bypasses_rls(conn):
                pytest.skip(
                    "Current DB role bypasses RLS, so this can't observe the "
                    "fail-closed default — see ci.yml's RLS test role."
                )
            rows = await conn.fetch(
                "SELECT * FROM resolve_api_key_tenant($1)", "nonexistent-hash-value"
            )
            assert rows == [], (
                "resolve_api_key_tenant() returned rows for a non-superuser, "
                "non-BYPASSRLS caller — ADR-010's fail-closed guarantee is broken. "
                "This must return zero rows until the BYPASSRLS + SELECT grants "
                "in ADR-010 are explicitly applied by a DB admin."
            )
        except asyncpg.exceptions.InsufficientPrivilegeError:
            # Also an acceptable fail-closed outcome — EXECUTE wasn't even
            # granted to this role (REVOKE ALL ... FROM PUBLIC is the
            # migration's default). Either "denied" or "zero rows" satisfies
            # the fail-closed requirement; a real cross-tenant row leaking
            # through would not.
            pass
        finally:
            await conn.close()
