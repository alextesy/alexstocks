"""add_llm_sentiment_to_daily_ticker_summary

Revision ID: 553177e8cc96
Revises: 9a2a65bbcc1c
Create Date: 2025-11-11 21:27:49.841181

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "553177e8cc96"
down_revision: str | Sequence[str] | None = "9a2a65bbcc1c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema - add llm_sentiment as enum."""
    # Create enum type
    op.execute(
        """
        CREATE TYPE llmsentimentcategory AS ENUM (
            '🚀 To the Moon',
            'Bullish',
            'Neutral',
            'Bearish',
            '💀 Doom'
        )
    """
    )

    # Add column with enum type
    op.add_column(
        "daily_ticker_summary",
        sa.Column(
            "llm_sentiment",
            sa.Enum(
                "🚀 To the Moon",
                "Bullish",
                "Neutral",
                "Bearish",
                "💀 Doom",
                name="llmsentimentcategory",
            ),
            nullable=True,
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("daily_ticker_summary", "llm_sentiment")
    op.execute("DROP TYPE llmsentimentcategory")
