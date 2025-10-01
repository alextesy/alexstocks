"""Add RedditThread table for tracking discussion thread scraping progress."""

import logging
import sys

from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError

from app.db.session import SessionLocal

logger = logging.getLogger(__name__)


def setup_logging() -> None:
    """Setup logging configuration."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )


def add_reddit_thread_table() -> None:
    """Add RedditThread table to track discussion thread scraping progress."""
    setup_logging()
    logger.info("Attempting to add RedditThread table...")

    db = SessionLocal()
    try:
        with db.begin():
            # Create RedditThread table
            db.execute(
                text("""
                CREATE TABLE IF NOT EXISTS reddit_thread (
                    reddit_id VARCHAR(20) PRIMARY KEY,
                    subreddit VARCHAR(50) NOT NULL,
                    title TEXT NOT NULL,
                    thread_type VARCHAR(20) NOT NULL,
                    url VARCHAR NOT NULL,
                    author VARCHAR(50),
                    upvotes INTEGER DEFAULT 0,
                    total_comments INTEGER NOT NULL DEFAULT 0,
                    scraped_comments INTEGER NOT NULL DEFAULT 0,
                    last_scraped_at TIMESTAMP WITH TIME ZONE,
                    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
                    is_complete BOOLEAN DEFAULT FALSE
                );
                """)
            )
            logger.info("Executing: CREATE TABLE reddit_thread...")

            # Add indexes
            db.execute(
                text("CREATE INDEX IF NOT EXISTS reddit_thread_subreddit_idx ON reddit_thread(subreddit);")
            )
            logger.info("Executing: CREATE INDEX reddit_thread_subreddit_idx...")

            db.execute(
                text("CREATE INDEX IF NOT EXISTS reddit_thread_type_idx ON reddit_thread(thread_type);")
            )
            logger.info("Executing: CREATE INDEX reddit_thread_type_idx...")

            db.execute(
                text("CREATE INDEX IF NOT EXISTS reddit_thread_last_scraped_idx ON reddit_thread(last_scraped_at DESC);")
            )
            logger.info("Executing: CREATE INDEX reddit_thread_last_scraped_idx...")

            db.execute(
                text("CREATE INDEX IF NOT EXISTS reddit_thread_created_idx ON reddit_thread(created_at DESC);")
            )
            logger.info("Executing: CREATE INDEX reddit_thread_created_idx...")

        logger.info("Successfully added RedditThread table and indexes")
        print("✅ RedditThread table added successfully")

    except ProgrammingError as e:
        logger.error(f"Database error during migration: {e}")
        print(f"❌ Database error: {e}")
        db.rollback()
    except Exception as e:
        logger.error(f"An unexpected error occurred: {e}")
        print(f"❌ An unexpected error occurred: {e}")
        db.rollback()
    finally:
        db.close()


if __name__ == "__main__":
    add_reddit_thread_table()
