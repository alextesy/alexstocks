"""Compact daily_ticker_summary.top_articles payloads.

Revision ID: c0d178e0fe0b
Revises: 5a8dff29d8f7
Create Date: 2026-02-14 00:10:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c0d178e0fe0b"
down_revision: str | Sequence[str] | None = "5a8dff29d8f7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Reduce top_articles payloads to just article IDs."""
    op.execute(
        """
        WITH transformed AS (
            SELECT
                id,
                CASE
                    WHEN top_articles IS NULL THEN NULL
                    ELSE (
                        SELECT jsonb_agg(to_jsonb((elem->>'article_id')::bigint))
                        FROM jsonb_array_elements(top_articles) AS elem
                        WHERE elem ? 'article_id'
                          AND (elem->>'article_id') ~ '^[0-9]+$'
                    )
                END AS new_top_articles
            FROM daily_ticker_summary
        )
        UPDATE daily_ticker_summary AS dts
        SET top_articles = transformed.new_top_articles
        FROM transformed
        WHERE dts.id = transformed.id
          AND transformed.new_top_articles IS DISTINCT FROM dts.top_articles
        """
    )


def downgrade() -> None:
    """Revert compact payloads (not reversible, so nullify)."""
    op.execute("UPDATE daily_ticker_summary SET top_articles = NULL")
