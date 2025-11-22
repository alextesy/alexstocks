"""
Fill Weekend/Holiday Gaps in Stock Price History.

This job fills gaps in stock price history (weekends, holidays) by forward-filling
from the last available trading day. This ensures charts display continuous data
even when markets are closed.

Usage:
    # Fill gaps for all tickers (last 90 days)
    uv run python -m jobs.jobs.fill_price_gaps

    # Fill gaps for specific tickers
    uv run python -m jobs.jobs.fill_price_gaps --symbols AAPL NVDA TSLA

    # Fill gaps for the last 180 days
    uv run python -m jobs.jobs.fill_price_gaps --days-back 180
"""

import argparse
import asyncio
import logging
import sys

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


async def run_gap_fill(
    symbols: list[str] | None = None,
    days_back: int = 90,
) -> dict:
    """
    Fill weekend/holiday gaps in stock price history.

    Args:
        symbols: Optional list of specific symbols to process
        days_back: How many days back to check for gaps (default: 90)

    Returns:
        Statistics dictionary
    """
    logger.info("Starting weekend/holiday gap fill job")
    if symbols:
        logger.info(f"Processing specific symbols: {symbols}")
    else:
        logger.info("Processing all symbols with historical data")

    # Initialize collector and run gap fill
    collector = StockPriceCollector()
    db = SessionLocal()

    try:
        result = await collector.fill_weekend_holiday_gaps(
            db=db,
            symbols=symbols,
            days_back=days_back,
        )

        logger.info("\nGap fill completed successfully:")
        logger.info(f"  Symbols processed: {result['symbols_processed']}")
        logger.info(f"  Days filled: {result['total_filled']}")

        return result

    finally:
        db.close()


def main() -> dict:
    """Entry point with argument parsing."""
    parser = argparse.ArgumentParser(
        description="Fill weekend/holiday gaps in stock price history"
    )
    parser.add_argument(
        "--symbols",
        nargs="+",
        type=str,
        help="Specific symbols to process (e.g., AAPL NVDA). If omitted, processes all symbols.",
    )
    parser.add_argument(
        "--days-back",
        type=int,
        default=90,
        help="How many days back to check for gaps (default: 90)",
    )

    args = parser.parse_args()

    return asyncio.run(
        run_gap_fill(
            symbols=args.symbols,
            days_back=args.days_back,
        )
    )


if __name__ == "__main__":
    run_with_slack(
        job_name="fill_stock_price_gaps",
        job_func=main,
        metadata={},
    )
