"""add append-only audit log"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0004_audit_log"
down_revision = "0003_gmail_credentials"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "audit_log",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("ts", sa.Text(), nullable=False),
        sa.Column("user_id", sa.Text(), nullable=False),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("target", sa.Text()),
        sa.Column("ip", sa.Text()),
        sa.Column("user_agent", sa.Text()),
        sa.Column("result", sa.Text(), nullable=False),
        sa.Column("detail_json", sa.Text()),
        sa.CheckConstraint("result IN ('success','denied','error')", name="ck_audit_log_result"),
    )
    op.create_index("idx_audit_log_user_ts", "audit_log", ["user_id", "ts"])
    op.create_index("idx_audit_log_action_ts", "audit_log", ["action", "ts"])


def downgrade() -> None:
    op.drop_index("idx_audit_log_action_ts", table_name="audit_log")
    op.drop_index("idx_audit_log_user_ts", table_name="audit_log")
    op.drop_table("audit_log")
