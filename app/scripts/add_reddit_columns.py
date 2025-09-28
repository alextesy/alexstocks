"""Add Reddit-specific columns to the article table."""

import logging
import sys
from sqlalchemy import text

from app.db.session import SessionLocal

logger = logging.getLogger(__name__)


def add_reddit_columns() -> None:
    """Add Reddit-specific columns to the article table."""
    db = SessionLocal()
    try:
        # Add Reddit-specific columns
        reddit_columns = [
            "ALTER TABLE article ADD COLUMN IF NOT EXISTS reddit_id VARCHAR(20) UNIQUE;",
            "ALTER TABLE article ADD COLUMN IF NOT EXISTS subreddit VARCHAR(50);",
            "ALTER TABLE article ADD COLUMN IF NOT EXISTS author VARCHAR(50);",
            "ALTER TABLE article ADD COLUMN IF NOT EXISTS upvotes INTEGER DEFAULT 0;",
            "ALTER TABLE article ADD COLUMN IF NOT EXISTS num_comments INTEGER DEFAULT 0;",
            "ALTER TABLE article ADD COLUMN IF NOT EXISTS reddit_url TEXT;",
        ]
        
        for sql in reddit_columns:
            logger.info(f"Executing: {sql}")
            db.execute(text(sql))
        
        # Add indexes for Reddit queries
        reddit_indexes = [
            "CREATE INDEX IF NOT EXISTS article_reddit_id_idx ON article(reddit_id);",
            "CREATE INDEX IF NOT EXISTS article_subreddit_idx ON article(subreddit);",
            "CREATE INDEX IF NOT EXISTS article_upvotes_idx ON article(upvotes DESC);",
        ]
        
        for sql in reddit_indexes:
            logger.info(f"Executing: {sql}")
            db.execute(text(sql))
        
        db.commit()
        logger.info("Successfully added Reddit columns and indexes")
        
    except Exception as e:
        logger.error(f"Error adding Reddit columns: {e}")
        db.rollback()
        raise
    finally:
        db.close()


def main() -> None:
    """Main entry point."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )
    
    try:
        add_reddit_columns()
        print("✅ Reddit columns added successfully")
    except Exception as e:
        print(f"❌ Error adding Reddit columns: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
