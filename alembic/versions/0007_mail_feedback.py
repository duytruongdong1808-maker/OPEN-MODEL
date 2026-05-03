"""add mail_triage_feedback table"""

from __future__ import annotations
from alembic import op
import sqlalchemy as sa

revision = "0007_mail_feedback"
down_revision = "0006_conversation_system_prompt"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "mail_triage_feedback",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("user_id", sa.Text(), nullable=False),
        sa.Column("message_id", sa.Text(), nullable=False),
        sa.Column("rating", sa.SmallInteger(), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False),
    )
    op.create_index("idx_mail_feedback_message_id", "mail_triage_feedback", ["message_id"])


def downgrade() -> None:
    op.drop_index("idx_mail_feedback_message_id", table_name="mail_triage_feedback")
    op.drop_table("mail_triage_feedback")
