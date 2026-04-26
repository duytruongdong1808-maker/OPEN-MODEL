"""add user ownership to conversations"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0002_conversation_user_id"
down_revision = "0001_baseline"
branch_labels = None
depends_on = None


def _conversation_columns() -> set[str]:
    inspector = sa.inspect(op.get_bind())
    return {column["name"] for column in inspector.get_columns("conversations")}


def upgrade() -> None:
    if "user_id" not in _conversation_columns():
        op.add_column(
            "conversations",
            sa.Column(
                "user_id",
                sa.Text(),
                nullable=False,
                server_default="legacy",
            ),
        )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_conversations_user_updated "
        "ON conversations(user_id, updated_at DESC)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_conversations_user_updated")
    if "user_id" in _conversation_columns():
        op.drop_column("conversations", "user_id")
