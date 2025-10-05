#!/usr/bin/env python3
"""Filter tickers to identify which are actively tradeable."""

import sys

sys.path.append(".")

import logging

from sqlalchemy import func

from app.db.models import StockPrice, Ticker
from app.db.session import SessionLocal

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def analyze_tickers():
    """Analyze ticker database to find potentially inactive tickers."""
    db = SessionLocal()

    try:
        total_tickers = db.query(func.count(Ticker.symbol)).scalar()
        logger.info(f"Total tickers in database: {total_tickers}")

        # Count tickers with price data
        tickers_with_prices = db.query(
            func.count(StockPrice.symbol.distinct())
        ).scalar()
        logger.info(f"Tickers with price data: {tickers_with_prices}")

        # Find potentially problematic ticker patterns
        patterns = {
            "Warrants (-WT, -WS)": db.query(func.count(Ticker.symbol))
            .filter(Ticker.symbol.like("%-WT"))
            .scalar()
            + db.query(func.count(Ticker.symbol))
            .filter(Ticker.symbol.like("%-WS"))
            .scalar(),
            "Units (-U)": db.query(func.count(Ticker.symbol))
            .filter(Ticker.symbol.like("%-U"))
            .scalar(),
            "Rights (-R)": db.query(func.count(Ticker.symbol))
            .filter(Ticker.symbol.like("%-R"))
            .scalar(),
            "Preferred Stock (ends with letter)": (
                db.query(func.count(Ticker.symbol))
                .filter(Ticker.symbol.regexp_match(r"[A-Z]$"))
                .scalar()
                if db.bind and db.bind.dialect.name == "postgresql"
                else 0
            ),
        }

        logger.info("\nPotentially inactive ticker types:")
        for pattern, count in patterns.items():
            if count > 0:
                logger.info(f"  {pattern}: {count}")

        # Suggest collection strategy
        logger.info("\n" + "=" * 60)
        logger.info("RECOMMENDATIONS:")
        logger.info("=" * 60)

        inactive_count = sum(patterns.values())
        active_estimate = total_tickers - inactive_count

        logger.info(
            f"Estimated active tickers: ~{active_estimate} ({active_estimate/total_tickers*100:.1f}%)"
        )
        logger.info(
            f"Estimated inactive tickers: ~{inactive_count} ({inactive_count/total_tickers*100:.1f}%)"
        )

        time_estimate_all = total_tickers * 1.5 / 60  # seconds to minutes
        time_estimate_active = active_estimate * 1.5 / 60

        logger.info("\nCollection time estimates (with rate limiting):")
        logger.info(f"  All tickers: ~{time_estimate_all:.0f} minutes")
        logger.info(f"  Active tickers only: ~{time_estimate_active:.0f} minutes")

        logger.info(
            "\nTo speed up collection, consider filtering out warrants, units, and rights."
        )

        # Show some examples of tickers without prices
        logger.info("\nSample tickers WITHOUT price data:")
        tickers_without_prices = (
            db.query(Ticker.symbol)
            .outerjoin(StockPrice, Ticker.symbol == StockPrice.symbol)
            .filter(StockPrice.symbol.is_(None))
            .limit(20)
            .all()
        )

        for ticker in tickers_without_prices:
            logger.info(f"  {ticker.symbol}")

    finally:
        db.close()


if __name__ == "__main__":
    analyze_tickers()
