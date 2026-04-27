"""use jsonb for audit details on postgres"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0005_audit_detail_jsonb"
down_revision = "0004_audit_log"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if op.get_context().dialect.name != "postgresql":
        return
    op.alter_column(
        "audit_log",
        "detail_json",
        existing_type=sa.Text(),
        type_=postgresql.JSONB(astext_type=sa.Text()),
        postgresql_using="detail_json::jsonb",
    )


def downgrade() -> None:
    if op.get_context().dialect.name != "postgresql":
        return
    op.alter_column(
        "audit_log",
        "detail_json",
        existing_type=postgresql.JSONB(astext_type=sa.Text()),
        type_=sa.Text(),
        postgresql_using="detail_json::text",
    )
