"""add_backfill_progress_table

Revision ID: 269070216a3d
Revises: 9b4400615dfb
Create Date: 2025-11-22 18:09:18.396697

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "269070216a3d"
down_revision: str | Sequence[str] | None = "9b4400615dfb"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema - add backfill_progress table for tracking historical data backfill."""
    op.create_table(
        "backfill_progress",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("run_id", sa.String(length=100), nullable=False),
        sa.Column("symbol", sa.String(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("records_inserted", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id", "symbol", name="uq_backfill_progress_run_symbol"),
    )
    op.create_index(
        "idx_backfill_progress_run_status",
        "backfill_progress",
        ["run_id", "status"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema - remove backfill_progress table."""
    op.drop_index("idx_backfill_progress_run_status", table_name="backfill_progress")
    op.drop_table("backfill_progress")
