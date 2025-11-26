"""
Hourly Historical Stock Price Append Job for Active Tickers.

Runs every hour (24/7) to keep historical data fresh for:
- All tickers with at least 10 article mentions (typically 50-200+ tickers)
- User-followed tickers

This ensures smooth hourly price charts and 24 data points for "Last 24 Hours" view.

Usage:
    # Run hourly for all active tickers (10+ articles) + followed tickers
    uv run python -m jobs.jobs.hourly_historical_append

    # Custom article threshold
    uv run python -m jobs.jobs.hourly_historical_append --min-articles 5

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


from sqlalchemy import func  # noqa: E402

from app.collectors.stock_price_collector import StockPriceCollector  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402

# Import slack_wrapper and ticker_utils - handle both local (jobs.jobs) and Docker (jobs) contexts
try:
    from jobs.slack_wrapper import run_with_slack  # Docker context
    from jobs.ticker_utils import get_followed_tickers  # Docker context
except ImportError:
    from jobs.jobs.slack_wrapper import run_with_slack  # Local context
    from jobs.jobs.ticker_utils import get_followed_tickers  # Local context

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
    min_articles: int = 10,
) -> dict:
    """
    Run the hourly historical price append job for active tickers.

    Args:
        top_n: Deprecated (kept for backward compatibility)
        include_followed: Whether to include user-followed tickers
        batch_size: Tickers per batch
        delay: Seconds between batches
        min_articles: Minimum article count threshold (default: 10)

    Returns:
        Statistics dictionary
    """
    logger.info(f"Hourly historical append starting at {datetime.now(UTC)}")
    logger.info(
        f"Processing tickers with at least {min_articles} article mentions + followed tickers"
    )

    # Initialize database session
    db = SessionLocal()

    try:
        # Get all active tickers (those with sufficient article coverage)
        # Same logic as daily_historical_append for consistency
        from app.db.models import ArticleTicker, Ticker

        active_tickers_subq = (
            db.query(ArticleTicker.ticker, func.count().label("article_count"))
            .group_by(ArticleTicker.ticker)
            .having(func.count() >= min_articles)
            .subquery()
        )

        active_tickers = (
            db.query(Ticker.symbol)
            .join(
                active_tickers_subq,
                Ticker.symbol == active_tickers_subq.c.ticker,
            )
            .order_by(Ticker.symbol)
            .all()
        )

        active_ticker_symbols = [symbol for (symbol,) in active_tickers]
        logger.info(
            f"Found {len(active_ticker_symbols)} active tickers with at least {min_articles} article mentions"
        )

        # Get followed tickers
        followed_tickers = []
        if include_followed:
            followed_tickers = get_followed_tickers(db)

        # Combine and deduplicate
        all_symbols = list(set(active_ticker_symbols + followed_tickers))
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
        description="Hourly append for active tickers (runs 24/7)"
    )
    parser.add_argument(
        "--top-n",
        type=int,
        default=50,
        help="Deprecated - kept for backward compatibility",
    )
    parser.add_argument(
        "--skip-followed",
        action="store_true",
        help="Skip user-followed tickers",
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
    parser.add_argument(
        "--min-articles",
        type=int,
        default=10,
        help="Minimum article count threshold (default: 10)",
    )

    args = parser.parse_args()

    return asyncio.run(
        run_hourly_append(
            top_n=args.top_n,
            include_followed=not args.skip_followed,
            batch_size=args.batch_size,
            delay=args.delay,
            min_articles=args.min_articles,
        )
    )


if __name__ == "__main__":
    run_with_slack(
        job_name="hourly_historical_stock_append",
        job_func=main,
        metadata={},
    )
