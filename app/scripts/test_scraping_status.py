"""Test script to add a sample scraping status entry."""

from datetime import UTC, datetime

from app.db.models import ScrapingStatus
from app.db.session import SessionLocal


def add_sample_status():
    """Add a sample scraping status for testing."""
    db = SessionLocal()
    try:
        # Check if status exists
        existing = (
            db.query(ScrapingStatus)
            .filter(ScrapingStatus.source == "reddit")
            .first()
        )

        if existing:
            print(f"Scraping status already exists for reddit")
            print(f"Last scrape: {existing.last_scrape_at}")
            print(f"Items scraped: {existing.items_scraped}")
            print(f"Status: {existing.status}")
            return

        # Create sample status
        status = ScrapingStatus(
            source="reddit",
            last_scrape_at=datetime.now(UTC),
            items_scraped=150,
            status="success",
            error_message=None,
            updated_at=datetime.now(UTC),
        )
        db.add(status)
        db.commit()
        print("✅ Sample scraping status added successfully")
        print(f"Last scrape: {status.last_scrape_at}")
        print(f"Items scraped: {status.items_scraped}")

    except Exception as e:
        print(f"❌ Error: {e}")
        db.rollback()
    finally:
        db.close()


if __name__ == "__main__":
    add_sample_status()
