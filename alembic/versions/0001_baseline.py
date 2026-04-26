"""baseline conversation schema"""
from __future__ import annotations

from alembic import op

revision = "0001_baseline"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS conversations (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS messages (
            id TEXT PRIMARY KEY,
            conversation_id TEXT NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('user', 'assistant')),
            content TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS message_sources (
            id TEXT PRIMARY KEY,
            message_id TEXT NOT NULL,
            title TEXT NOT NULL,
            source TEXT NOT NULL,
            published_at TEXT,
            url TEXT NOT NULL,
            position INTEGER NOT NULL,
            FOREIGN KEY(message_id) REFERENCES messages(id) ON DELETE CASCADE
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_conversations_updated_at "
        "ON conversations(updated_at DESC)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_messages_conversation_id "
        "ON messages(conversation_id, created_at)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_message_sources_message_id "
        "ON message_sources(message_id, position)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_message_sources_message_id")
    op.execute("DROP INDEX IF EXISTS idx_messages_conversation_id")
    op.execute("DROP INDEX IF EXISTS idx_conversations_updated_at")
    op.execute("DROP TABLE IF EXISTS message_sources")
    op.execute("DROP TABLE IF EXISTS messages")
    op.execute("DROP TABLE IF EXISTS conversations")
