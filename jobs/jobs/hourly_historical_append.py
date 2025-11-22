"""
Hourly Historical Stock Price Append Job for Top Tickers.

Runs every hour during market hours to keep historical data fresh for:
- Top 50 tickers by article mentions
- User-followed tickers

Usage:
    # Run hourly for top 50 + followed tickers
    uv run python -m jobs.jobs.hourly_historical_append

    # Custom top N
    uv run python -m jobs.jobs.hourly_historical_append --top-n 100

    # Skip followed tickers
    uv run python -m jobs.jobs.hourly_historical_append --skip-followed
"""

import argparse
import asyncio
import logging
import sys
from datetime import UTC, datetime

# Load environment variables FIRST
from dotenv import load_dotenv

load_dotenv()

# Add project root to path
sys.path.append(".")


from app.collectors.stock_price_collector import StockPriceCollector  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402

# Import slack_wrapper and ticker_utils - handle both local (jobs.jobs) and Docker (jobs) contexts
try:
    from jobs.slack_wrapper import run_with_slack  # Docker context
    from jobs.ticker_utils import (  # Docker context
        get_followed_tickers,
        get_top_n_tickers,
    )
except ImportError:
    from jobs.jobs.slack_wrapper import run_with_slack  # Local context
    from jobs.jobs.ticker_utils import (  # Local context
        get_followed_tickers,
        get_top_n_tickers,
    )

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


async def run_hourly_append(
    top_n: int = 50,
    include_followed: bool = True,
    batch_size: int = 10,
    delay: float = 0.5,
) -> dict:
    """
    Run the hourly historical price append job for top tickers.

    Args:
        top_n: Number of top tickers by mentions to include
        include_followed: Whether to include user-followed tickers
        batch_size: Tickers per batch
        delay: Seconds between batches

    Returns:
        Statistics dictionary
    """
    logger.info(f"Hourly historical append starting at {datetime.now(UTC)}")
    logger.info(f"Processing top {top_n} tickers (last 24h) + followed tickers")

    # Initialize database session
    db = SessionLocal()

    try:
        # Get top N tickers from last 24 hours (same logic as stock_price_collector)
        top_tickers = get_top_n_tickers(db, n=top_n, hours=24)
        logger.info(
            f"Found {len(top_tickers)} top tickers in last 24h (excluding ETFs)"
        )

        # Get followed tickers
        followed_tickers = []
        if include_followed:
            followed_tickers = get_followed_tickers(db)

        # Combine and deduplicate
        all_symbols = list(set(top_tickers + followed_tickers))
        logger.info(f"Total unique tickers to process: {len(all_symbols)}")

        if not all_symbols:
            logger.warning("No tickers found to process")
            return {
                "success": 0,
                "failed": 0,
                "skipped": 0,
                "total_records_inserted": 0,
                "errors": [],
            }

        # Initialize collector and run append
        collector = StockPriceCollector()

        result = await collector.collect_daily_historical_append(
            db=db,
            symbols=all_symbols,
            days_back=1,  # Only look back 1 day for hourly updates
            batch_size=batch_size,
            delay_between_batches=delay,
            min_article_threshold=None,  # We already filtered
        )

        logger.info(
            f"Hourly append completed: {result['success']} success, "
            f"{result['failed']} failed, {result['skipped']} skipped, "
            f"{result['total_records_inserted']} records inserted"
        )

        return result

    finally:
        db.close()


def main() -> dict:
    """Entry point with argument parsing."""
    parser = argparse.ArgumentParser(
        description="Hourly append for top tickers during market hours"
    )
    parser.add_argument(
        "--top-n",
        type=int,
        default=50,
        help="Number of top tickers to include (default: 50)",
    )
    parser.add_argument(
        "--skip-followed",
        action="store_true",
        help="Skip user-followed tickers (only process top N)",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=10,
        help="Number of tickers per batch (default: 10)",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=0.5,
        help="Seconds to wait between batches (default: 0.5)",
    )

    args = parser.parse_args()

    return asyncio.run(
        run_hourly_append(
            top_n=args.top_n,
            include_followed=not args.skip_followed,
            batch_size=args.batch_size,
            delay=args.delay,
        )
    )


if __name__ == "__main__":
    run_with_slack(
        job_name="hourly_historical_stock_append",
        job_func=main,
        metadata={},
    )
