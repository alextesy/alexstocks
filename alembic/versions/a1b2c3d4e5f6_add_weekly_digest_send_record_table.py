"""add_weekly_digest_send_record_table

Revision ID: a1b2c3d4e5f6
Revises: 269070216a3d
Create Date: 2025-12-05 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: str | Sequence[str] | None = "269070216a3d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "weekly_digest_send_record",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("week_start_date", sa.Date(), nullable=False),
        sa.Column(
            "status", sa.String(length=20), nullable=False, server_default="pending"
        ),
        sa.Column("ticker_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("days_with_data", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("message_id", sa.String(length=255), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("skip_reason", sa.String(length=100), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id", "week_start_date", name="uq_weekly_digest_user_week"
        ),
    )
    op.create_index(
        "weekly_digest_week_status_idx",
        "weekly_digest_send_record",
        ["week_start_date", "status"],
        unique=False,
    )
    op.create_index(
        "weekly_digest_user_idx",
        "weekly_digest_send_record",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        "weekly_digest_created_idx",
        "weekly_digest_send_record",
        [sa.literal_column("created_at DESC")],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("weekly_digest_created_idx", table_name="weekly_digest_send_record")
    op.drop_index("weekly_digest_user_idx", table_name="weekly_digest_send_record")
    op.drop_index(
        "weekly_digest_week_status_idx", table_name="weekly_digest_send_record"
    )
    op.drop_table("weekly_digest_send_record")
