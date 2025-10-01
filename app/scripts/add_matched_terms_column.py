"""Add matched_terms column to article_ticker table."""

import logging

from sqlalchemy import text

from app.db.session import SessionLocal

logger = logging.getLogger(__name__)


def add_matched_terms_column():
    """Adds the matched_terms column to the article_ticker table if it doesn't exist."""
    db = SessionLocal()

    try:
        # Check if the column already exists
        result = db.execute(text("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = 'article_ticker'
            AND column_name = 'matched_terms'
        """))

        if result.fetchone():
            logger.info("matched_terms column already exists. Skipping creation.")
            print("✅ matched_terms column already exists")
            return

        logger.info("Adding matched_terms column to article_ticker table...")

        # Add the column
        db.execute(text("""
            ALTER TABLE article_ticker
            ADD COLUMN matched_terms JSONB
        """))

        db.commit()
        logger.info("Successfully added matched_terms column")
        print("✅ matched_terms column added successfully")

    except Exception as e:
        db.rollback()
        logger.error(f"Error adding matched_terms column: {e}")
        print(f"❌ Error adding matched_terms column: {e}")
    finally:
        db.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    add_matched_terms_column()
