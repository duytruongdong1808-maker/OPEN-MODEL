"""add append-only audit log"""
from __future__ import annotations

from alembic import op

revision = "0004_audit_log"
down_revision = "0003_gmail_credentials"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT NOT NULL,
            user_id TEXT NOT NULL,
            action TEXT NOT NULL,
            target TEXT,
            ip TEXT,
            user_agent TEXT,
            result TEXT NOT NULL CHECK(result IN ('success','denied','error')),
            detail_json TEXT
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_audit_log_user_ts "
        "ON audit_log(user_id, ts DESC)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_audit_log_action_ts "
        "ON audit_log(action, ts DESC)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_audit_log_action_ts")
    op.execute("DROP INDEX IF EXISTS idx_audit_log_user_ts")
    op.execute("DROP TABLE IF EXISTS audit_log")
