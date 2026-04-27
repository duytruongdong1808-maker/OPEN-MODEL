"""add per-user Gmail credentials"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0003_gmail_credentials"
down_revision = "0002_conversation_user_id"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "gmail_credentials",
        sa.Column("user_id", sa.Text(), primary_key=True),
        sa.Column("encrypted_token", sa.LargeBinary(), nullable=False),
        sa.Column("email", sa.Text()),
        sa.Column("scopes", sa.Text()),
        sa.Column("connected_at", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("gmail_credentials")
