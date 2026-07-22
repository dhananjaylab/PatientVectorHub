"""add ingestion_jobs, documents, api_keys, audit_logs, query_logs

Revision ID: 004
Revises: 003
Create Date: 2026-07-19 00:00:00

Completes the Phase 2 "Database Foundation" schema from doc 05 (8 tables
total; 001-003 delivered tenants/users/patients). All five new tables are
tenant-scoped except none-of-them-are-tenants-itself, so all five get
FORCE ROW LEVEL SECURITY exactly like migration 003's users/patients,
fail-closed by the same current_setting('app.tenant_id', true) mechanism.

Two deliberate deviations from the original design docs, both fixing real
bugs rather than just restyling:

1. audit_logs append-only enforcement. Doc 13 showed a single policy:
       CREATE POLICY audit_logs_tenant ON audit_logs
         USING      (tenant_id = current_setting('app.tenant_id')::UUID)
         WITH CHECK (FALSE);
   A single policy with no `FOR <command>` clause applies to ALL commands,
   including INSERT — so WITH CHECK (FALSE) would have rejected every
   insert too, not just UPDATE/DELETE, silently breaking audit logging
   entirely. This migration instead defines separate SELECT and INSERT
   policies and deliberately defines NO UPDATE/DELETE policy at all.
   Under RLS, a command with zero applicable policies is denied outright
   for any non-superuser/non-BYPASSRLS role — that's what actually makes
   the table append-only, not a WITH CHECK (FALSE) policy.

2. API key authentication vs. RLS bootstrapping (ADR-010). Resolving an
   inbound `X-API-Key` header to a tenant_id is a chicken-and-egg problem:
   the api_keys table is tenant-scoped and FORCE RLS'd, but you don't know
   which tenant to SET before you've looked the key up. resolve_api_key_tenant()
   below is written as the standard Postgres answer to this (a SECURITY
   DEFINER function). Verified empirically against a real Postgres instance:
   it works immediately in local dev (the migrating role, `pvh`, is a
   bootstrap superuser, and superusers unconditionally bypass RLS regardless
   of FORCE), but on managed Postgres where the migrating role is NOT a
   superuser (Aiven's avnadmin, RDS's master user, etc.), the function
   returns zero rows until a DB admin separately grants BYPASSRLS *and* a
   plain SELECT on api_keys to its owning role, OUT OF BAND — the same way
   CI's `pvh_rls_test` role is created by a shell step, not by Alembic,
   because the app's normal migrating role does not reliably have
   CREATEROLE on managed Postgres. Until those grants happen in a given
   non-superuser environment, this function returns zero rows for every
   lookup, which means API-key authentication fails closed (401), not open.
   See docs/adr/ADR-010-api-key-auth-rls-bootstrap.md for the full grant
   sequence and the test that verified this.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "004"
down_revision = "003"
branch_labels = None
depends_on = None

# Tenant-scoped tables added in this migration — same FORCE RLS treatment
# as migration 003 applied to users/patients.
_STANDARD_RLS_TABLES = ["ingestion_jobs", "documents", "api_keys", "query_logs"]


def upgrade() -> None:
    # ── ingestion_jobs (created before documents — documents.ingestion_job_id FKs to it) ──
    op.create_table(
        "ingestion_jobs",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="queued"),
        sa.Column("source_type", sa.String(length=32), nullable=False),
        sa.Column(
            "source_config", postgresql.JSONB(astext_type=sa.Text()), nullable=False,
            server_default="{}",
        ),
        sa.Column("doc_count_total", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("doc_count_processed", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("doc_count_failed", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id")),
        sa.Column(
            "tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id"),
            nullable=False,
        ),
        sa.Column("started_at", sa.TIMESTAMP(timezone=True)),
        sa.Column("completed_at", sa.TIMESTAMP(timezone=True)),
        sa.Column("error_message", sa.Text()),
        sa.Column(
            "created_at", sa.TIMESTAMP(timezone=True), nullable=False,
            server_default=sa.text("NOW()"),
        ),
    )
    op.create_check_constraint(
        "ck_ingestion_jobs_status", "ingestion_jobs",
        "status IN ('queued','running','completed','failed','cancelled')",
    )
    op.create_check_constraint(
        "ck_ingestion_jobs_source_type", "ingestion_jobs",
        "source_type IN ('s3_batch','kafka_stream','api_push')",
    )
    op.create_index("ix_ingestion_jobs_tenant_id", "ingestion_jobs", ["tenant_id"])
    op.create_index("ix_ingestion_jobs_status", "ingestion_jobs", ["status"])

    # ── documents ──────────────────────────────────────────────────────────
    op.create_table(
        "documents",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column(
            "patient_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("patients.id"),
            nullable=False,
        ),
        sa.Column("document_type", sa.String(length=32), nullable=False),
        sa.Column("source_path", sa.Text(), nullable=False),
        sa.Column(
            "ingestion_job_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("ingestion_jobs.id"),
        ),
        sa.Column(
            "embedding_status", sa.String(length=32), nullable=False, server_default="pending",
        ),
        sa.Column("chunk_count", sa.Integer()),
        sa.Column("model_version", sa.String(length=128)),
        sa.Column("vector_store", sa.String(length=32), nullable=False, server_default="weaviate"),
        sa.Column(
            "tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id"),
            nullable=False,
        ),
        sa.Column(
            "ingested_at", sa.TIMESTAMP(timezone=True), nullable=False,
            server_default=sa.text("NOW()"),
        ),
    )
    op.create_check_constraint(
        "ck_documents_document_type", "documents",
        "document_type IN ('clinical_note','lab_result','imaging_report',"
        "'discharge_summary','prescription')",
    )
    op.create_check_constraint(
        "ck_documents_embedding_status", "documents",
        "embedding_status IN ('pending','processing','completed','failed')",
    )
    op.create_index("ix_documents_patient_id", "documents", ["patient_id"])
    op.create_index("ix_documents_tenant_id", "documents", ["tenant_id"])
    # Partial index — fast queue scan for the ingestion worker (doc 13's pattern)
    op.execute(
        "CREATE INDEX ix_documents_pending ON documents (embedding_status) "
        "WHERE embedding_status != 'completed'"
    )

    # ── api_keys ───────────────────────────────────────────────────────────
    op.create_table(
        "api_keys",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column("key_hash", sa.String(length=64), nullable=False, unique=True),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column(
            "scopes", postgresql.ARRAY(sa.String()), nullable=False, server_default="{}",
        ),
        sa.Column(
            "user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False,
        ),
        sa.Column(
            "tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("is_revoked", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("last_used_at", sa.TIMESTAMP(timezone=True)),
        sa.Column(
            "created_at", sa.TIMESTAMP(timezone=True), nullable=False,
            server_default=sa.text("NOW()"),
        ),
    )
    op.create_index("ix_api_keys_tenant_id", "api_keys", ["tenant_id"])

    # ── query_logs ─────────────────────────────────────────────────────────
    op.create_table(
        "query_logs",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column(
            "tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id"),
            nullable=False,
        ),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id")),
        sa.Column("query_text_hash", sa.String(length=64), nullable=False),
        sa.Column("result_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("latency_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("model_version", sa.String(length=128)),
        sa.Column(
            "created_at", sa.TIMESTAMP(timezone=True), nullable=False,
            server_default=sa.text("NOW()"),
        ),
    )
    op.create_index("ix_query_logs_tenant_id", "query_logs", ["tenant_id"])
    op.create_index("ix_query_logs_created_at", "query_logs", ["created_at"])

    # ── audit_logs — append-only (see module docstring, point 1) ────────────
    op.create_table(
        "audit_logs",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id")),
        sa.Column("api_key_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("api_keys.id")),
        sa.Column("action", sa.String(length=32), nullable=False),
        sa.Column("patient_id", postgresql.UUID(as_uuid=True)),
        sa.Column("ip_address", sa.String(length=64)),
        sa.Column("request_id", sa.String(length=64)),
        sa.Column("status_code", sa.Integer()),
        sa.Column(
            "metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False,
            server_default="{}",
        ),
        sa.Column(
            "tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id"),
            nullable=False,
        ),
        sa.Column(
            "created_at", sa.TIMESTAMP(timezone=True), nullable=False,
            server_default=sa.text("NOW()"),
        ),
    )
    op.create_check_constraint(
        "ck_audit_logs_action", "audit_logs",
        "action IN ('document_query','document_ingest','phi_reveal','api_key_create',"
        "'api_key_revoke','user_login','settings_change','data_export')",
    )
    op.create_index("ix_audit_logs_tenant_id", "audit_logs", ["tenant_id"])
    op.create_index("ix_audit_logs_created_at", "audit_logs", ["created_at"])

    # ── RLS: standard tenant isolation on the 4 CRUD-able tables ────────────
    for table in _STANDARD_RLS_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"""
            CREATE POLICY {table}_tenant_isolation ON {table}
            USING      (tenant_id = current_setting('app.tenant_id', true)::uuid)
            WITH CHECK (tenant_id = current_setting('app.tenant_id', true)::uuid)
            """
        )

    # ── RLS: audit_logs — SELECT + INSERT only, no UPDATE/DELETE policy at all ──
    op.execute("ALTER TABLE audit_logs ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE audit_logs FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY audit_logs_select ON audit_logs
        FOR SELECT
        USING (tenant_id = current_setting('app.tenant_id', true)::uuid)
        """
    )
    op.execute(
        """
        CREATE POLICY audit_logs_insert ON audit_logs
        FOR INSERT
        WITH CHECK (tenant_id = current_setting('app.tenant_id', true)::uuid)
        """
    )
    # Deliberately no FOR UPDATE / FOR DELETE policy — see module docstring.

    # ── API key resolver function (ADR-010) ─────────────────────────────────
    # SECURITY DEFINER so it *can* bypass RLS, but only does so once its
    # owning role is separately granted BYPASSRLS by a DB admin — see the
    # module docstring and ADR-010. Until then this returns zero rows,
    # which is the safe, fail-closed default.
    op.execute(
        """
        CREATE OR REPLACE FUNCTION resolve_api_key_tenant(p_key_hash text)
        RETURNS TABLE (
            key_id      uuid,
            tenant_id   uuid,
            user_id     uuid,
            scopes      text[],
            is_revoked  boolean,
            expires_at  timestamptz
        )
        LANGUAGE sql
        SECURITY DEFINER
        SET search_path = public
        AS $$
            SELECT id, tenant_id, user_id, scopes, is_revoked, expires_at
            FROM api_keys
            WHERE key_hash = p_key_hash
        $$
        """
    )
    op.execute("REVOKE ALL ON FUNCTION resolve_api_key_tenant(text) FROM PUBLIC")


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS resolve_api_key_tenant(text)")

    op.execute("DROP POLICY IF EXISTS audit_logs_insert ON audit_logs")
    op.execute("DROP POLICY IF EXISTS audit_logs_select ON audit_logs")
    op.execute("ALTER TABLE audit_logs NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE audit_logs DISABLE ROW LEVEL SECURITY")
    op.drop_table("audit_logs")

    for table in reversed(_STANDARD_RLS_TABLES):
        op.execute(f"DROP POLICY IF EXISTS {table}_tenant_isolation ON {table}")
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")

    op.drop_table("query_logs")
    op.drop_table("api_keys")
    op.drop_table("documents")
    op.drop_table("ingestion_jobs")
