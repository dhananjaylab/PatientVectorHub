"""add access_denied to audit_logs.action

Revision ID: 005
Revises: 004
Create Date: 2026-08-22 00:00:00

Phase 10 (Observability & Security) / ADR-017.

migration 004's ck_audit_logs_action constraint has 8 values, none of
which fit a *failed* access attempt (a 401 with no valid credential, or
a 403 RBAC denial). Without this, middleware/audit_log.py's
AuditLogMiddleware has nowhere valid to record one -- Postgres would
reject the INSERT outright (CHECK constraint violation) the first time
it tried.

Deliberately NOT adding a value for authentication failures with no
established tenant context (a bare 401, credential missing/invalid
entirely) -- see middleware/audit_log.py's own docstring for why:
audit_logs is FORCE RLS'd and every row must carry a real tenant_id
scoped via current_setting('app.tenant_id'); a request that never
authenticated has no tenant to scope a row to, so attempting one there
would itself violate RLS, not just be semantically odd. 'access_denied'
is therefore scoped specifically to 403s -- authentication succeeded
(tenant_id IS known), the resolved role just lacked permission for the
route. A bare 401's failed-attempt trail lives in the structured JSON
access logs (logging_config.py) instead, which need no tenant context.
"""
from alembic import op

revision = "005"
down_revision = "004"
branch_labels = None
depends_on = None

_OLD_ACTIONS = (
    "document_query", "document_ingest", "phi_reveal", "api_key_create",
    "api_key_revoke", "user_login", "settings_change", "data_export",
)
_NEW_ACTIONS = _OLD_ACTIONS + ("access_denied",)


def _in_clause(actions: tuple[str, ...]) -> str:
    return "action IN (" + ",".join(f"'{a}'" for a in actions) + ")"


def upgrade() -> None:
    op.drop_constraint("ck_audit_logs_action", "audit_logs", type_="check")
    op.create_check_constraint(
        "ck_audit_logs_action", "audit_logs", _in_clause(_NEW_ACTIONS)
    )


def downgrade() -> None:
    # Any 'access_denied' rows written under the new constraint would
    # violate the old one on downgrade -- fail loudly rather than
    # silently corrupt history by deleting audit rows in a "downgrade".
    op.execute(
        "DO $$ BEGIN "
        "IF EXISTS (SELECT 1 FROM audit_logs WHERE action = 'access_denied') THEN "
        "RAISE EXCEPTION "
        "'Cannot downgrade: audit_logs has rows with action=access_denied. "
        "Audit trail rows must never be deleted to satisfy a schema downgrade.'; "
        "END IF; END $$;"
    )
    op.drop_constraint("ck_audit_logs_action", "audit_logs", type_="check")
    op.create_check_constraint(
        "ck_audit_logs_action", "audit_logs", _in_clause(_OLD_ACTIONS)
    )
