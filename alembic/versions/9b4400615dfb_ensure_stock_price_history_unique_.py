"""ensure_stock_price_history_unique_constraint

Revision ID: 9b4400615dfb
Revises: 7bbbee342bd
Create Date: 2025-11-22 17:38:53.407129

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "9b4400615dfb"
down_revision: str | Sequence[str] | None = "7bbbee342bd"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_unique_constraint(
        "uq_stock_price_history_symbol_date",
        "stock_price_history",
        ["symbol", "date"],
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint(
        "uq_stock_price_history_symbol_date", "stock_price_history", type_="unique"
    )
