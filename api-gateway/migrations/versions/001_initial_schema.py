"""initial schema placeholder

Revision ID: 001
Revises:
Create Date: 2025-06-01 00:00:00

Phase 1: empty migration — proves Alembic wiring works.
Phase 2 adds the real table DDL.
"""
from alembic import op

# revision identifiers
revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Phase 1: no tables yet — verify Alembic can connect and run
    op.execute("SELECT 1")


def downgrade() -> None:
    pass
