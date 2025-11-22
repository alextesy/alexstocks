"""
Daily Historical Stock Price Append Job.

Appends missing historical stock price data for all tickers by:
- Finding the last date in stock_price_history for each ticker
- Fetching data from last_date + 1 to now
- Inserting any missing records

Can also be run for specific tickers (useful when adding new tickers).

Usage:
    # Run for all tickers (daily append)
    uv run python -m jobs.jobs.daily_historical_append

    # Run for specific ticker (e.g., newly added ticker)
    uv run python -m jobs.jobs.daily_historical_append --symbols AAPL NVDA

    # Backfill new ticker from October 2025 to now
    uv run python -m jobs.jobs.daily_historical_append --symbols NEWTKR --days-back 60

    # Adjust batch size and delay
    uv run python -m jobs.jobs.daily_historical_append --batch-size 20 --delay 0.5
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

# Import slack_wrapper - handle both local (jobs.jobs) and Docker (jobs) contexts
try:
    from jobs.slack_wrapper import run_with_slack  # Docker context
except ImportError:
    from jobs.jobs.slack_wrapper import run_with_slack  # Local context

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


async def run_daily_append(
    symbols: list[str] | None = None,
    days_back: int = 7,
    batch_size: int = 10,
    delay: float = 1.0,
    min_articles: int = 10,
    fill_gaps: bool = True,
) -> dict:
    """
    Run the daily historical price append job.

    Args:
        symbols: Optional list of specific symbols to process
        days_back: Maximum days to look back if no history exists
        batch_size: Tickers per batch
        delay: Seconds between batches
        min_articles: Minimum article count threshold (default: 10)
        fill_gaps: Whether to fill weekend/holiday gaps after appending (default: True)

    Returns:
        Statistics dictionary
    """
    logger.info(f"Daily historical append starting at {datetime.now(UTC)}")
    if symbols:
        logger.info(f"Processing specific symbols: {symbols}")
    else:
        logger.info(f"Processing tickers with at least {min_articles} article mentions")

    # Initialize collector and run append
    collector = StockPriceCollector()
    db = SessionLocal()

    try:
        result = await collector.collect_daily_historical_append(
            db=db,
            symbols=symbols,
            days_back=days_back,
            batch_size=batch_size,
            delay_between_batches=delay,
            min_article_threshold=min_articles,
        )

        # Fill weekend/holiday gaps after appending new data
        if fill_gaps:
            logger.info("\n" + "=" * 80)
            logger.info("Running weekend/holiday gap filling...")
            logger.info("=" * 80 + "\n")

            gap_fill_result = await collector.fill_weekend_holiday_gaps(
                db=db, symbols=symbols, days_back=max(days_back, 90)
            )

            result["gap_fill"] = gap_fill_result

        return result

    finally:
        db.close()


def main() -> dict:
    """Entry point with argument parsing."""
    parser = argparse.ArgumentParser(
        description="Append missing historical stock prices daily"
    )
    parser.add_argument(
        "--symbols",
        nargs="+",
        type=str,
        help="Specific symbols to process (e.g., AAPL NVDA). If omitted, processes all tickers.",
    )
    parser.add_argument(
        "--days-back",
        type=int,
        default=7,
        help="Maximum days to look back if no history exists (default: 7)",
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
        default=1.0,
        help="Seconds to wait between batches (default: 1.0)",
    )
    parser.add_argument(
        "--min-articles",
        type=int,
        default=10,
        help="Minimum article count threshold (default: 10)",
    )
    parser.add_argument(
        "--no-fill-gaps",
        action="store_true",
        help="Skip weekend/holiday gap filling (default: gaps are filled)",
    )

    args = parser.parse_args()

    return asyncio.run(
        run_daily_append(
            symbols=args.symbols,
            days_back=args.days_back,
            batch_size=args.batch_size,
            delay=args.delay,
            min_articles=args.min_articles,
            fill_gaps=not args.no_fill_gaps,
        )
    )


if __name__ == "__main__":
    run_with_slack(
        job_name="daily_historical_stock_append",
        job_func=main,
        metadata={},
    )
