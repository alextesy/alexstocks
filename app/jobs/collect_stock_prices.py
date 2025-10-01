"""Job to collect current stock prices and store in database."""

import asyncio
import logging
import sys
from datetime import datetime

# Add project root to path
sys.path.append('.')

from app.collectors.stock_price_collector import StockPriceCollector
from app.db.session import SessionLocal

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def collect_current_prices():
    """Collect current stock prices for all tickers."""
    logger.info("Starting stock price collection job")

    collector = StockPriceCollector()
    db = SessionLocal()

    try:
        result = await collector.collect_current_prices(db)

        logger.info(
            f"Stock price collection completed: "
            f"{result['success']} success, {result['failed']} failed, "
            f"duration: {result['duration']:.2f}s"
        )

        if result['errors']:
            logger.warning(f"Errors encountered: {result['errors'][:5]}")  # Log first 5 errors

        return result

    except Exception as e:
        logger.error(f"Stock price collection job failed: {e}")
        raise
    finally:
        db.close()


async def collect_historical_data():
    """Collect historical stock price data (run less frequently)."""
    logger.info("Starting historical stock data collection job")

    collector = StockPriceCollector()
    db = SessionLocal()

    try:
        result = await collector.collect_historical_data(db, period="1mo")

        logger.info(
            f"Historical data collection completed: "
            f"{result['success']} success, {result['failed']} failed, "
            f"duration: {result['duration']:.2f}s"
        )

        if result['errors']:
            logger.warning(f"Errors encountered: {result['errors'][:5]}")

        return result

    except Exception as e:
        logger.error(f"Historical data collection job failed: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description='Collect stock price data')
    parser.add_argument(
        '--type',
        choices=['current', 'historical', 'both'],
        default='current',
        help='Type of data to collect'
    )

    args = parser.parse_args()

    async def main():
        start_time = datetime.now()

        if args.type in ['current', 'both']:
            await collect_current_prices()

        if args.type in ['historical', 'both']:
            await collect_historical_data()

        total_time = (datetime.now() - start_time).total_seconds()
        logger.info(f"Total job time: {total_time:.2f}s")

    asyncio.run(main())

