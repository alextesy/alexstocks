"""
Test historical stock price backfill with top 5 tickers.

Quick test script to validate backfill functionality before running full job.
Uses only the top 5 most-mentioned tickers to minimize API calls.
"""

import argparse
import asyncio
import logging
import sys
import uuid
from datetime import UTC, datetime

# Load environment variables FIRST
from dotenv import load_dotenv

load_dotenv()

# Add project root to path
sys.path.append(".")


from sqlalchemy import func  # noqa: E402

from app.collectors.stock_price_collector import StockPriceCollector  # noqa: E402
from app.db.models import ArticleTicker  # noqa: E402
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


def parse_date(date_str: str) -> datetime:
    """Parse date string in YYYY-MM-DD format to timezone-aware datetime."""
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        return dt.replace(tzinfo=UTC)
    except ValueError as e:
        raise ValueError(f"Invalid date format '{date_str}'. Use YYYY-MM-DD.") from e


async def run_test_backfill(
    start_date: str | None = None,
    end_date: str | None = None,
    top_n: int = 5,
) -> dict:
    """
    Run backfill test with top N most-mentioned tickers.

    Args:
        start_date: Start date in YYYY-MM-DD format
        end_date: End date in YYYY-MM-DD format (defaults to today)
        top_n: Number of top tickers to test (default 5)

    Returns:
        Statistics dictionary
    """
    # Generate unique test run ID
    run_id = f"test-backfill-{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:8]}"
    logger.info(f"🧪 Test Run ID: {run_id}")

    # Parse dates
    if start_date:
        start_dt = parse_date(start_date)
    else:
        # Default: last 7 days for quick test
        start_dt = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
        start_dt = start_dt.replace(day=start_dt.day - 7)

    if end_date:
        end_dt = parse_date(end_date)
    else:
        end_dt = datetime.now(UTC)

    logger.info(f"📅 Test date range: {start_dt.date()} to {end_dt.date()}")

    # Get top N most-mentioned tickers
    db = SessionLocal()
    try:
        top_tickers = (
            db.query(ArticleTicker.ticker, func.count().label("mention_count"))
            .group_by(ArticleTicker.ticker)
            .order_by(func.count().desc())
            .limit(top_n)
            .all()
        )

        test_symbols = [ticker for ticker, count in top_tickers]

        if not test_symbols:
            logger.warning("No tickers found in database!")
            return {
                "run_id": run_id,
                "requested": 0,
                "success": 0,
                "failed": 0,
                "skipped": 0,
                "rate_limited": 0,
                "errors": [],
            }

        logger.info(f"🎯 Testing with top {len(test_symbols)} tickers: {test_symbols}")
        logger.info(f"   Mention counts: {[(t, c) for t, c in top_tickers]}")

        # Initialize collector
        collector = StockPriceCollector()

        # Run backfill with special test parameters
        result = await collector.collect_historical_backfill(
            db=db,
            run_id=run_id,
            start_date=start_dt,
            end_date=end_dt,
            min_article_threshold=0,  # Skip article threshold for test
            batch_size=top_n,  # Process all in one batch
            delay_between_batches=1.0,  # Shorter delay for test
            resume=False,  # Always start fresh for tests
        )

        # Add test symbols to result for reference
        result["test_symbols"] = test_symbols

        return result

    finally:
        db.close()


def main() -> dict:
    """Entry point with argument parsing."""
    parser = argparse.ArgumentParser(
        description="Test historical backfill with top 5 tickers"
    )
    parser.add_argument(
        "--start-date",
        type=str,
        help="Start date in YYYY-MM-DD format (default: 7 days ago)",
    )
    parser.add_argument(
        "--end-date",
        type=str,
        help="End date in YYYY-MM-DD format (default: today)",
    )
    parser.add_argument(
        "--top-n",
        type=int,
        default=5,
        help="Number of top tickers to test (default: 5)",
    )

    args = parser.parse_args()

    return asyncio.run(
        run_test_backfill(
            start_date=args.start_date,
            end_date=args.end_date,
            top_n=args.top_n,
        )
    )


if __name__ == "__main__":
    run_with_slack(
        job_name="test_historical_backfill",
        job_func=main,
        metadata={},
    )
