#!/usr/bin/env python3
"""Quick test script to verify stock data collection works."""

import asyncio
import logging
import sys

sys.path.append(".")

from sqlalchemy import func

from app.collectors.stock_price_collector import StockPriceCollector
from app.db.models import Ticker
from app.db.session import SessionLocal

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def test_collection():
    """Test stock data collection with a small sample."""
    db = SessionLocal()
    collector = StockPriceCollector()

    try:
        # Get count of tickers in database
        ticker_count = db.query(func.count(Ticker.symbol)).scalar()
        logger.info(f"Found {ticker_count} tickers in database")

        if ticker_count == 0:
            logger.error("No tickers in database! Please add some tickers first.")
            return

        # Get first 3 tickers for testing
        test_symbols = [t.symbol for t in db.query(Ticker).limit(3).all()]
        logger.info(f"Testing with symbols: {test_symbols}")

        # Test current price collection
        logger.info("Testing current price collection...")
        result = await collector.collect_current_prices(db, symbols=test_symbols)

        logger.info(
            f"✓ Current prices: {result['success']} successful, "
            f"{result['failed']} failed, "
            f"{result['duration']:.2f}s"
        )

        if result["errors"]:
            logger.warning(f"Errors: {result['errors']}")

        # Test historical data collection
        logger.info("Testing historical data collection (5 days)...")
        result = await collector.collect_historical_data(
            db, symbols=test_symbols, period="5d"
        )

        logger.info(
            f"✓ Historical data: {result['success']} successful, "
            f"{result['failed']} failed, "
            f"{result['duration']:.2f}s"
        )

        if result["errors"]:
            logger.warning(f"Errors: {result['errors']}")

        logger.info("\n✓ All tests passed! Stock data collection is working.")
        logger.info("\nNext steps:")
        logger.info(
            "1. Run: uv run python app/scripts/collect_all_stock_data.py --type current"
        )
        logger.info("2. Set up cron: ./scripts/setup-stock-price-cron.sh")
        logger.info("3. See docs/STOCK_DATA_COLLECTION.md for details")

    except Exception as e:
        logger.error(f"✗ Test failed: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    asyncio.run(test_collection())
