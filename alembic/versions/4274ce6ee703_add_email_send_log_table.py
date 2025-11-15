"""add_email_send_log_table

Revision ID: 4274ce6ee703
Revises: c0d178e0fe0b
Create Date: 2025-11-15 16:51:39.441651

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "4274ce6ee703"
down_revision: str | Sequence[str] | None = "c0d178e0fe0b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "email_send_log",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("email_address", sa.String(length=255), nullable=False),
        sa.Column("summary_date", sa.Date(), nullable=False),
        sa.Column("ticker_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("success", sa.Boolean(), nullable=False),
        sa.Column("message_id", sa.String(length=255), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("provider", sa.String(length=50), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "email_send_log_user_idx", "email_send_log", ["user_id"], unique=False
    )
    op.create_index(
        "email_send_log_summary_date_idx",
        "email_send_log",
        ["summary_date"],
        unique=False,
    )
    op.create_index(
        "email_send_log_sent_at_idx",
        "email_send_log",
        [sa.literal_column("sent_at DESC")],
        unique=False,
    )
    op.create_index(
        "email_send_log_success_idx", "email_send_log", ["success"], unique=False
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("email_send_log_success_idx", table_name="email_send_log")
    op.drop_index("email_send_log_sent_at_idx", table_name="email_send_log")
    op.drop_index("email_send_log_summary_date_idx", table_name="email_send_log")
    op.drop_index("email_send_log_user_idx", table_name="email_send_log")
    op.drop_table("email_send_log")
