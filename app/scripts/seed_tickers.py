"""Seed ticker data from CSV file."""

import csv
import json
import logging
from pathlib import Path

from app.config import settings
from app.db.models import Ticker
from app.db.session import SessionLocal

logger = logging.getLogger(__name__)


def load_tickers_from_csv(csv_path: Path) -> list[dict]:
    """Load ticker data from CSV file."""
    tickers: list[dict] = []

    if not csv_path.exists():
        logger.error(f"Ticker CSV file not found: {csv_path}")
        return tickers

    try:
        with open(csv_path, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                # Parse aliases JSON string
                aliases = []
                if row.get("aliases"):
                    try:
                        aliases = json.loads(row["aliases"])
                    except json.JSONDecodeError:
                        logger.warning(
                            f"Invalid aliases JSON for {row['symbol']}: {row['aliases']}"
                        )

                # Parse sources
                sources: list[str] = []
                if row.get("sources"):
                    sources = row["sources"].split(",")

                # Parse boolean
                is_sp500 = row.get("is_sp500", "").lower() in ("true", "1", "yes")

                ticker_data = {
                    "symbol": row["symbol"].strip().upper(),
                    "name": row["name"].strip(),
                    "aliases": aliases,
                    "exchange": row.get("exchange") or None,
                    "sources": sources,
                    "is_sp500": is_sp500,
                    "cik": row.get("cik") or None,
                }
                tickers.append(ticker_data)

        logger.info(f"Loaded {len(tickers)} tickers from {csv_path}")
        return tickers

    except Exception as e:
        logger.error(f"Failed to load tickers from CSV: {e}")
        return []


def seed_tickers(tickers: list[dict]) -> bool:
    """Seed the database with ticker data."""
    if not tickers:
        logger.error("No ticker data to seed")
        return False

    db = SessionLocal()
    try:
        # Clear existing tickers and related data (handle foreign key constraints)
        # First delete article_ticker references, then tickers
        from app.db.models import ArticleTicker

        db.query(ArticleTicker).delete()
        db.query(Ticker).delete()
        db.commit()
        logger.info("Cleared existing ticker data")

        # Insert new tickers
        inserted_count = 0
        for ticker_data in tickers:
            try:
                ticker = Ticker(
                    symbol=ticker_data["symbol"],
                    name=ticker_data["name"],
                    aliases=ticker_data["aliases"],
                    exchange=ticker_data.get("exchange"),
                    sources=ticker_data.get("sources", []),
                    is_sp500=ticker_data.get("is_sp500", False),
                    cik=ticker_data.get("cik"),
                )
                db.add(ticker)
                inserted_count += 1
            except Exception as e:
                logger.warning(f"Failed to insert ticker {ticker_data['symbol']}: {e}")

        db.commit()
        logger.info(f"Successfully seeded {inserted_count} tickers")

        # Verify insertion
        total_count = db.query(Ticker).count()
        logger.info(f"Total tickers in database: {total_count}")

        return True

    except Exception as e:
        logger.error(f"Failed to seed tickers: {e}")
        db.rollback()
        return False
    finally:
        db.close()


def main() -> None:
    """Main function for ticker seeding."""
    logging.basicConfig(level=logging.INFO)
    logger.info("Starting ticker seeding...")

    # Load tickers from CSV
    csv_path = Path(settings.tickers_path)
    tickers = load_tickers_from_csv(csv_path)

    if not tickers:
        logger.error("No tickers loaded, exiting")
        return

    # Seed database
    success = seed_tickers(tickers)

    if success:
        logger.info("Ticker seeding completed successfully")
    else:
        logger.error("Ticker seeding failed")


if __name__ == "__main__":
    main()
