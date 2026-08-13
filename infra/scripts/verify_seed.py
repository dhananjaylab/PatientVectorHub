#!/usr/bin/env python3
"""
Verify seeded PostgreSQL data — RLS-aware.

Why this exists (not just a `SELECT COUNT(*)` one-liner)
----------------------------------------------------------
After migration 003_enable_rls.py, `users` and `patients` run under
FORCE ROW LEVEL SECURITY. A plain `SELECT COUNT(*) FROM users` from a
connection that never sets `app.tenant_id` doesn't error — it just
returns 0, because RLS filters every row out of visibility. That's the
correct fail-closed behaviour for the app, but it makes a naive
verification query silently lie about whether seeding worked.

This script sums counts per tenant, setting app.tenant_id before each
query, so the totals are accurate on Aiven (non-superuser role) as well
as local Docker Compose Postgres (where POSTGRES_USER happens to be a
superuser and bypasses RLS anyway, masking the difference).

Usage:
    python scripts/verify_seed.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from seed_data import TENANT_A, TENANT_B, TENANTS, get_database_url  # noqa: E402

try:
    from sqlalchemy import create_engine, text
except ImportError:
    print("SQLAlchemy not installed - cannot verify")
    sys.exit(1)


def main() -> None:
    engine = create_engine(get_database_url(), pool_pre_ping=True)

    with engine.connect() as conn:
        revision = conn.execute(
            text("SELECT version_num FROM alembic_version")
        ).scalar()
        print(f"revision   {revision}")

        # tenants has no tenant_id column and is not RLS-scoped —
        # a plain count is accurate regardless of role/GUC.
        tenant_count = conn.execute(text("SELECT COUNT(*) FROM tenants")).scalar()
        print(f"tenants    {tenant_count}")

        total_users = 0
        total_patients = 0
        for t in TENANTS:
            tid = t["id"]
            conn.execute(
                text("SELECT set_config('app.tenant_id', :tid, true)"),
                {"tid": tid},
            )
            users = conn.execute(text("SELECT COUNT(*) FROM users")).scalar()
            patients = conn.execute(text("SELECT COUNT(*) FROM patients")).scalar()
            print(f"  {t['name']:<20} users={users:<4} patients={patients}")
            total_users += users
            total_patients += patients

        print(f"users      {total_users}")
        print(f"patients   {total_patients}")

        expected_users = len(TENANTS) * 4       # 4 roles per tenant
        expected_patients = len(TENANTS) * 1000
        ok = (
            tenant_count == len(TENANTS)
            and total_users == expected_users
            and total_patients == expected_patients
        )
        print("")
        if ok:
            print("OK — counts match expected seed output.")
        else:
            print(
                f"MISMATCH — expected tenants={len(TENANTS)} "
                f"users={expected_users} patients={expected_patients}. "
                "If this is Aiven and counts are 0, confirm scripts/seed_data.py "
                "ran AFTER migration 003_enable_rls.py's _set_tenant_context() fix "
                "was applied, not before."
            )
            sys.exit(1)


if __name__ == "__main__":
    main()