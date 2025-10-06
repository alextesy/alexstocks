#!/usr/bin/env python3
"""Smart stock data collection - filters out likely inactive tickers."""

import asyncio
import logging
import sys

sys.path.append(".")

from sqlalchemy import or_

from app.collectors.stock_price_collector import StockPriceCollector
from app.db.models import Ticker
from app.db.session import SessionLocal

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def get_active_tickers(db, exclude_patterns: bool = True):
    """Get list of likely active tickers (exclude warrants, units, rights)."""
    query = db.query(Ticker.symbol)

    if exclude_patterns:
        # Exclude common inactive ticker patterns
        query = query.filter(
            ~or_(
                Ticker.symbol.like("%-WT"),  # Warrants
                Ticker.symbol.like("%-WS"),  # Warrants
                Ticker.symbol.like("%-U"),  # Units
                Ticker.symbol.like("%-R"),  # Rights
                Ticker.symbol.like("%+"),  # Special class
                Ticker.symbol.like("%.%"),  # Foreign/ADR variations
            )
        )

    symbols = [t.symbol for t in query.all()]
    return symbols


async def collect_smart(
    collection_type: str = "current",
    exclude_inactive: bool = True,
    period: str = "1mo",
    force_refresh: bool = False,
    limit: int | None = None,
):
    """Smart collection that filters out likely inactive tickers."""
    db = SessionLocal()
    collector = StockPriceCollector()

    try:
        # Get list of tickers
        if exclude_inactive:
            symbols = get_active_tickers(db, exclude_patterns=True)
            logger.info(f"Using smart filtering - {len(symbols)} likely active tickers")
        else:
            symbols = [t.symbol for t in db.query(Ticker).all()]
            logger.info(f"Using all tickers - {len(symbols)} total")

        # Limit for testing
        if limit:
            symbols = symbols[:limit]
            logger.info(f"Limited to first {limit} tickers for testing")

        # Estimate time
        estimated_seconds = len(symbols) * 1.5  # ~1.5s per ticker with rate limiting
        estimated_minutes = estimated_seconds / 60
        logger.info(
            f"Estimated collection time: ~{estimated_minutes:.1f} minutes ({estimated_seconds:.0f} seconds)"
        )

        # Collect data
        if collection_type in ["current", "both"]:
            logger.info("Collecting current prices...")
            result = await collector.collect_current_prices(db, symbols=symbols)
            logger.info(
                f"✓ Current prices: {result['success']} success, "
                f"{result['failed']} failed, {result['duration']:.1f}s"
            )

        if collection_type in ["historical", "both"]:
            logger.info(f"Collecting historical data (period={period})...")
            result = await collector.collect_historical_data(
                db, symbols=symbols, period=period, force_refresh=force_refresh
            )
            logger.info(
                f"✓ Historical data: {result['success']} success, "
                f"{result['failed']} failed, {result['duration']:.1f}s"
            )

        logger.info("\n✓ Collection complete!")

    except Exception as e:
        logger.error(f"Collection failed: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Smart stock data collection (filters inactive tickers)"
    )
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
        "--no-filter",
        action="store_true",
        help="Don't filter out inactive tickers (collect ALL)",
    )
    parser.add_argument(
        "--force-refresh",
        action="store_true",
        help="Force refresh historical data",
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="Limit number of tickers (for testing)",
    )

    args = parser.parse_args()

    asyncio.run(
        collect_smart(
            collection_type=args.type,
            exclude_inactive=not args.no_filter,
            period=args.period,
            force_refresh=args.force_refresh,
            limit=args.limit,
        )
    )
