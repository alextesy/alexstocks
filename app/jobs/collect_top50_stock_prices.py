"""Job to collect stock prices for top 50 most active tickers."""

import asyncio
import logging
import sys
from datetime import datetime

# Add project root to path
sys.path.append(".")

from app.db.session import SessionLocal
from app.services.stock_price_service import stock_price_service

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


async def collect_top50_prices():
    """
    Collect current stock prices for the top 50 most active tickers.

    This job is designed to run every 15 minutes via cron to keep
    the homepage prices fresh.
    """
    start_time = datetime.now()
    logger.info("=" * 80)
    logger.info("Starting Top 50 stock price collection job")
    logger.info("=" * 80)

    db = SessionLocal()

    try:
        # Run the refresh
        result = await stock_price_service.refresh_top_n_prices(db, n=50)

        duration = (datetime.now() - start_time).total_seconds()

        # Log results
        logger.info("-" * 80)
        logger.info("Collection Results:")
        logger.info(f"  Requested: {result['requested']}")
        logger.info(f"  Successful: {result['success']}")
        logger.info(f"  Failed: {result['failed']}")
        logger.info(f"  Duration: {duration:.2f}s")

        if result["errors"]:
            logger.warning(f"  Errors (showing first 10): {result['errors']}")

        logger.info("=" * 80)
        logger.info(f"Top 50 stock price collection completed in {duration:.2f}s")
        logger.info("=" * 80)

        return result

    except Exception as e:
        logger.error(f"Top 50 stock price collection job failed: {e}", exc_info=True)
        raise
    finally:
        db.close()


if __name__ == "__main__":
    asyncio.run(collect_top50_prices())
