"""add per-user Gmail credentials"""

from __future__ import annotations

from alembic import op

revision = "0003_gmail_credentials"
down_revision = "0002_conversation_user_id"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS gmail_credentials (
            user_id TEXT PRIMARY KEY,
            encrypted_token BLOB NOT NULL,
            email TEXT,
            scopes TEXT,
            connected_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS gmail_credentials")
