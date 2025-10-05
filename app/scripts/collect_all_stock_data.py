#!/usr/bin/env python3
"""Script to collect stock data for all tickers in the database."""

import asyncio
import logging
import sys

sys.path.append(".")

from app.collectors.stock_price_collector import StockPriceCollector
from app.db.session import SessionLocal

# Set up logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


async def collect_all_current_prices():
    """Collect current stock prices for all tickers in database."""
    logger.info("Starting stock price collection for all tickers")

    collector = StockPriceCollector()
    db = SessionLocal()

    try:
        # Pass symbols=None to collect ALL tickers
        result = await collector.collect_current_prices(db)

        logger.info(
            f"Collection completed: "
            f"{result['success']} successful, "
            f"{result['failed']} failed, "
            f"duration: {result['duration']:.2f}s"
        )

        if result["errors"]:
            logger.warning(f"Errors: {result['errors'][:5]}")  # Show first 5 errors

        return result

    except Exception as e:
        logger.error(f"Collection failed: {e}")
        raise
    finally:
        db.close()


async def collect_all_historical_data(period: str = "1mo", force_refresh: bool = False):
    """Collect historical stock data for all tickers in database."""
    logger.info(
        f"Starting historical data collection for all tickers (period={period})"
    )

    collector = StockPriceCollector()
    db = SessionLocal()

    try:
        result = await collector.collect_historical_data(
            db, symbols=None, period=period, force_refresh=force_refresh  # All tickers
        )

        logger.info(
            f"Historical collection completed: "
            f"{result['success']} successful, "
            f"{result['failed']} failed, "
            f"duration: {result['duration']:.2f}s"
        )

        if result["errors"]:
            logger.warning(f"Errors: {result['errors'][:5]}")

        return result

    except Exception as e:
        logger.error(f"Historical collection failed: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Collect stock data for all tickers")
    parser.add_argument(
        "--type",
        choices=["current", "historical", "both"],
        default="current",
        help="Type of data to collect",
    )
    parser.add_argument(
        "--period",
        choices=["1d", "5d", "1mo", "3mo", "6mo", "1y", "2y", "5y"],
        default="1mo",
        help="Period for historical data",
    )
    parser.add_argument(
        "--force-refresh",
        action="store_true",
        help="Force refresh historical data (delete and re-collect)",
    )

    args = parser.parse_args()

    async def main():
        if args.type in ["current", "both"]:
            await collect_all_current_prices()

        if args.type in ["historical", "both"]:
            await collect_all_historical_data(
                period=args.period, force_refresh=args.force_refresh
            )

    asyncio.run(main())
