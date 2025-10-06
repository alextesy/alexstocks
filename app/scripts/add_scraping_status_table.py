"""Add ScrapingStatus table for tracking scraping status across different sources."""

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


def add_scraping_status_table() -> None:
    """Add ScrapingStatus table to track scraping status."""
    setup_logging()
    logger.info("Attempting to add ScrapingStatus table...")

    db = SessionLocal()
    try:
        with db.begin():
            # Create ScrapingStatus table
            db.execute(
                text(
                    """
                CREATE TABLE IF NOT EXISTS scraping_status (
                    source VARCHAR(50) PRIMARY KEY,
                    last_scrape_at TIMESTAMP WITH TIME ZONE NOT NULL,
                    items_scraped INTEGER NOT NULL DEFAULT 0,
                    status VARCHAR(20) NOT NULL DEFAULT 'success',
                    error_message TEXT,
                    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
                );
                """
                )
            )
            logger.info("Executing: CREATE TABLE scraping_status...")

        logger.info("Successfully added ScrapingStatus table")
        print("✅ ScrapingStatus table added successfully")

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
    add_scraping_status_table()
