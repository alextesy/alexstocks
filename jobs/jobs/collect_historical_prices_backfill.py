"""
Historical stock price backfill job.

Backfills hourly stock price data starting from a configurable date
for active tickers. Designed to be durable and resumable in case of
rate limits or failures.

Usage:
    # Start new backfill run
    uv run python -m jobs.jobs.collect_historical_prices_backfill

    # Resume existing run by ID
    uv run python -m jobs.jobs.collect_historical_prices_backfill --run-id YOUR_RUN_ID

    # Custom date range
    uv run python -m jobs.jobs.collect_historical_prices_backfill --start-date 2025-10-01 --end-date 2025-11-01

    # Adjust article threshold
    uv run python -m jobs.jobs.collect_historical_prices_backfill --min-articles 5
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


from app.collectors.stock_price_collector import StockPriceCollector  # noqa: E402
from app.config import Settings  # noqa: E402
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


async def run_backfill(
    run_id: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    min_articles: int = 10,
    batch_size: int = 5,
    delay: float = 2.0,
    resume: bool = True,
) -> dict:
    """
    Run the historical price backfill job.

    Args:
        run_id: Unique run ID (generates new if None)
        start_date: Start date in YYYY-MM-DD format
        end_date: End date in YYYY-MM-DD format (defaults to today)
        min_articles: Minimum article count threshold
        batch_size: Tickers per batch
        delay: Seconds between batches
        resume: Whether to resume from previous run

    Returns:
        Statistics dictionary
    """
    settings = Settings()

    # Generate or use provided run ID
    if run_id is None:
        run_id = f"backfill-{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:8]}"
        logger.info(f"Generated new run ID: {run_id}")
    else:
        logger.info(f"Using provided run ID: {run_id}")

    # Parse dates
    if start_date:
        start_dt = parse_date(start_date)
    else:
        # Default to configured start date (October 1, 2025)
        start_dt = datetime(
            2025,
            settings.historical_backfill_start_month,
            settings.historical_backfill_start_day,
            tzinfo=UTC,
        )

    if end_date:
        end_dt = parse_date(end_date)
    else:
        end_dt = datetime.now(UTC)

    logger.info(f"Backfill date range: {start_dt.date()} to {end_dt.date()}")

    # Initialize collector and run backfill
    collector = StockPriceCollector()
    db = SessionLocal()

    try:
        result = await collector.collect_historical_backfill(
            db=db,
            run_id=run_id,
            start_date=start_dt,
            end_date=end_dt,
            min_article_threshold=min_articles,
            batch_size=batch_size,
            delay_between_batches=delay,
            resume=resume,
        )

        return result

    finally:
        db.close()


def main() -> dict:
    """Entry point with argument parsing."""
    parser = argparse.ArgumentParser(
        description="Backfill historical stock prices with durability"
    )
    parser.add_argument(
        "--run-id",
        type=str,
        help="Run ID to resume existing backfill (generates new if omitted)",
    )
    parser.add_argument(
        "--start-date",
        type=str,
        help="Start date in YYYY-MM-DD format (default: 2025-10-01)",
    )
    parser.add_argument(
        "--end-date",
        type=str,
        help="End date in YYYY-MM-DD format (default: today)",
    )
    parser.add_argument(
        "--min-articles",
        type=int,
        default=10,
        help="Minimum article count threshold (default: 10)",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=5,
        help="Number of tickers per batch (default: 5)",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=2.0,
        help="Seconds to wait between batches (default: 2.0)",
    )
    parser.add_argument(
        "--no-resume",
        action="store_true",
        help="Start fresh (don't resume from previous progress)",
    )

    args = parser.parse_args()

    return asyncio.run(
        run_backfill(
            run_id=args.run_id,
            start_date=args.start_date,
            end_date=args.end_date,
            min_articles=args.min_articles,
            batch_size=args.batch_size,
            delay=args.delay,
            resume=not args.no_resume,
        )
    )


if __name__ == "__main__":
    run_with_slack(
        job_name="historical_stock_price_backfill",
        job_func=main,
        metadata={},
    )
