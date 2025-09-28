"""Add sentiment column to article table."""

import logging

from sqlalchemy import text

from app.db.session import engine

logger = logging.getLogger(__name__)


def add_sentiment_column() -> None:
    """Add sentiment column to article table."""

    try:
        with engine.connect() as conn:
            # Check if column already exists
            result = conn.execute(
                text(
                    """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = 'article' AND column_name = 'sentiment'
            """
                )
            )

            if result.fetchone():
                logger.info("Sentiment column already exists")
                return

            # Add sentiment column
            conn.execute(
                text(
                    """
                ALTER TABLE article
                ADD COLUMN sentiment FLOAT
            """
                )
            )

            conn.commit()
            logger.info("Successfully added sentiment column to article table")

    except Exception as e:
        logger.error(f"Failed to add sentiment column: {e}")
        raise


if __name__ == "__main__":
    add_sentiment_column()
