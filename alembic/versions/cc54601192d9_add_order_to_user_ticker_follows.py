"""add_order_to_user_ticker_follows

Revision ID: cc54601192d9
Revises: 7a6b96aac112
Create Date: 2025-11-01 14:06:54.114626

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "cc54601192d9"
down_revision: str | Sequence[str] | None = "7a6b96aac112"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # Add order column (nullable initially for existing rows)
    op.add_column(
        "user_ticker_follows",
        sa.Column("order", sa.Integer(), nullable=True),
    )

    # Set order for existing rows based on created_at (older = lower order)
    op.execute(
        """
        UPDATE user_ticker_follows
        SET "order" = subquery.row_num - 1
        FROM (
            SELECT id, ROW_NUMBER() OVER (PARTITION BY user_id ORDER BY created_at ASC) as row_num
            FROM user_ticker_follows
        ) AS subquery
        WHERE user_ticker_follows.id = subquery.id
        """
    )

    # Make order non-nullable with default
    op.alter_column(
        "user_ticker_follows",
        "order",
        nullable=False,
        server_default=sa.text("0"),
    )

    # Create index for ordering queries
    op.create_index(
        "user_ticker_follow_order_idx",
        "user_ticker_follows",
        ["user_id", "order"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("user_ticker_follow_order_idx", table_name="user_ticker_follows")
    op.drop_column("user_ticker_follows", "order")
