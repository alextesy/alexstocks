"""Add daily ticker summary table"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.sql import text

# revision identifiers, used by Alembic.
revision = "9a2a65bbcc1c"
down_revision = "cc54601192d9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "daily_ticker_summary",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("ticker", sa.String(), nullable=False),
        sa.Column("summary_date", sa.Date(), nullable=False),
        sa.Column(
            "mention_count", sa.Integer(), nullable=False, server_default=sa.text("0")
        ),
        sa.Column(
            "engagement_count",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column("avg_sentiment", sa.Float(), nullable=True),
        sa.Column("sentiment_stddev", sa.Float(), nullable=True),
        sa.Column("sentiment_min", sa.Float(), nullable=True),
        sa.Column("sentiment_max", sa.Float(), nullable=True),
        sa.Column("top_articles", postgresql.JSONB(), nullable=True),
        sa.Column("llm_summary", sa.Text(), nullable=True),
        sa.Column("llm_summary_bullets", postgresql.JSONB(), nullable=True),
        sa.Column("llm_model", sa.String(length=100), nullable=True),
        sa.Column("llm_version", sa.String(length=100), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("timezone('utc', now())"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("timezone('utc', now())"),
            server_onupdate=sa.text("timezone('utc', now())"),
        ),
        sa.ForeignKeyConstraint(["ticker"], ["ticker.symbol"], ondelete="CASCADE"),
        sa.UniqueConstraint("ticker", "summary_date", name="uq_daily_ticker_summary"),
    )

    op.execute(
        text(
            "CREATE INDEX ix_daily_ticker_summary_ticker_summary_date_desc "
            "ON daily_ticker_summary (ticker, summary_date DESC)"
        )
    )


def downgrade() -> None:
    op.execute(
        text("DROP INDEX IF EXISTS ix_daily_ticker_summary_ticker_summary_date_desc")
    )
    op.drop_table("daily_ticker_summary")
