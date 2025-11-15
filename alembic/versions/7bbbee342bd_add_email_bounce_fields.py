"""add_email_bounce_fields

Revision ID: 7bbbee342bd
Revises: 4274ce6ee703
Create Date: 2025-01-27 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "7bbbee342bd"
down_revision: str | Sequence[str] | None = "4274ce6ee703"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "user_notification_channels",
        sa.Column(
            "email_bounced", sa.Boolean(), nullable=False, server_default="false"
        ),
    )
    op.add_column(
        "user_notification_channels",
        sa.Column("bounced_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "user_notification_channels",
        sa.Column("bounce_type", sa.String(length=50), nullable=True),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("user_notification_channels", "bounce_type")
    op.drop_column("user_notification_channels", "bounced_at")
    op.drop_column("user_notification_channels", "email_bounced")
