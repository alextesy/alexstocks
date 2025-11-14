"""Add engagement_score column to article.

Revision ID: 5a8dff29d8f7
Revises: 553177e8cc96
Create Date: 2026-02-14 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "5a8dff29d8f7"
down_revision: str | Sequence[str] | None = "553177e8cc96"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add engagement_score column and backfill existing rows."""
    op.add_column("article", sa.Column("engagement_score", sa.Float(), nullable=True))
    op.execute(
        """
        UPDATE article
        SET engagement_score =
            0.7 * ln(1 + GREATEST(COALESCE(upvotes, 0), 0)) +
            0.3 * ln(1 + GREATEST(COALESCE(num_comments, 0), 0))
        """
    )


def downgrade() -> None:
    """Drop engagement_score column."""
    op.drop_column("article", "engagement_score")
