"""enable row level security + tenant isolation policies

Revision ID: 003
Revises: 002
Create Date: 2026-07-18 00:00:00

Closes the Phase 1 risk-register gap: "PostgreSQL RLS policy silently
returns wrong rows for tenant isolation" (Critical / HIPAA).

Every tenant-scoped table gets:
  1. ROW LEVEL SECURITY enabled and FORCED (so table owners are not
     silently exempt from the policy — FORCE ROW LEVEL SECURITY matters
     because the app connects as the table-owning role in local/dev).
  2. A USING policy that requires
     tenant_id = current_setting('app.tenant_id')::uuid
     for SELECT / UPDATE / DELETE.
  3. A matching WITH CHECK clause so INSERT/UPDATE cannot write rows
     into a different tenant's namespace even if tenant_id is spoofed
     in the payload.

`tenants` itself is intentionally excluded — it is the root table and
has no tenant_id column to scope against.

Application code must call:
    SET LOCAL app.tenant_id = '<uuid>';
inside every request-scoped transaction before touching these tables
(see get_tenant_session() in db/session.py, added when Phase 2 CRUD
lands). Until that helper exists, any connection that does not set
app.tenant_id will see zero rows from every tenant-scoped table —
fail-closed by design, not fail-open.
"""
from alembic import op

# revision identifiers
revision = "003"
down_revision = "002"
branch_labels = None
depends_on = None

# Tables that carry a tenant_id column and must be tenant-isolated.
_TENANT_SCOPED_TABLES = ["users", "patients"]


def upgrade() -> None:
    for table in _TENANT_SCOPED_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        # FORCE ensures the policy also applies to the table owner —
        # without this, the app's own DB role (which typically owns
        # the tables it migrates) would bypass RLS entirely.
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")

        op.execute(
            f"""
            CREATE POLICY {table}_tenant_isolation ON {table}
            USING      (tenant_id = current_setting('app.tenant_id', true)::uuid)
            WITH CHECK (tenant_id = current_setting('app.tenant_id', true)::uuid)
            """
        )

    # No extra default is required: current_setting('app.tenant_id', true)
    # returns NULL when the GUC was never SET LOCAL for the session, and
    # `tenant_id = NULL` is always UNKNOWN in Postgres — so any connection
    # that forgets to SET LOCAL app.tenant_id sees zero rows from every
    # tenant-scoped table. Fail-closed by construction, not fail-open.


def downgrade() -> None:
    for table in _TENANT_SCOPED_TABLES:
        op.execute(f"DROP POLICY IF EXISTS {table}_tenant_isolation ON {table}")
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
