"""add per-conversation system prompt override"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0006_conversation_system_prompt"
down_revision = "0005_audit_detail_jsonb"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("conversations", sa.Column("system_prompt_override", sa.Text()))


def downgrade() -> None:
    op.drop_column("conversations", "system_prompt_override")
