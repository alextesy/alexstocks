#!/usr/bin/env python3
"""Remove problematic tickers that are common English words."""

import logging

from app.db.models import ArticleTicker, Ticker
from app.db.session import get_db

logger = logging.getLogger(__name__)

# Tickers to keep (important ones)
KEEP_TICKERS: set[str] = {
    "SPY",
    "MU",
    "TSLA",
    "NVDA",
    "AMZN",
    "GOOGL",
    "GOOG",
    "BABA",
    "ORCL",
    "INTC",
    "UNH",
    "SNAP",
    "MSFT",
    "AAPL",
    "META",
    "FB",
    "COST",
    "LOW",
    "V",
    "T",
    "DJCO",
    "RDDT",
    "OKLO",
    "LAC",
    "UUUU",
    "IREN",
    "BITF",
    "NBIS",
    "EOD",
    "WWW",
    "BRO",
    "PRE",
    "TRUE",
    "TECH",
}

# Problematic tickers that are common English words
PROBLEMATIC_TICKERS: set[str] = {
    "DON",
    "PUMP",
    "YEAR",
    "WANT",
    "WAY",
    "WELL",
    "SAY",
    "REAL",
    "COM",
    "PORT",
    "EVER",
    "AGO",
    "PLAY",
    "LOVE",
    "HIT",
    "MAN",
    "SHE",
    "NICE",
    "HOPE",
    "JOB",
    "CASH",
    "LOT",
    "SUB",
    "PAY",
}


def remove_problematic_tickers(dry_run: bool = True) -> None:
    """Remove problematic tickers that are common English words.

    Args:
        dry_run: If True, only show what would be changed without making changes
    """
    db = next(get_db())

    # Get all tickers
    all_tickers = db.query(Ticker).all()

    # Identify tickers to remove
    tickers_to_remove = []
    for ticker in all_tickers:
        if ticker.symbol in PROBLEMATIC_TICKERS and ticker.symbol not in KEEP_TICKERS:
            tickers_to_remove.append(ticker)

    if dry_run:
        print(f"Would remove {len(tickers_to_remove)} problematic tickers:")
        for ticker in tickers_to_remove:
            # Count articles linked to this ticker
            article_count = (
                db.query(ArticleTicker)
                .filter(ArticleTicker.ticker == ticker.symbol)
                .count()
            )
            print(f"  {ticker.symbol} - {ticker.name} ({article_count} articles)")

        print(f"\nWould keep {len(KEEP_TICKERS)} important tickers:")
        for symbol in KEEP_TICKERS:
            ticker = db.query(Ticker).filter(Ticker.symbol == symbol).first()
            if ticker:
                article_count = (
                    db.query(ArticleTicker)
                    .filter(ArticleTicker.ticker == symbol)
                    .count()
                )
                print(f"  {symbol} - {ticker.name} ({article_count} articles)")

        print("\nTo apply changes, run with --apply flag")
    else:
        removed_count = 0
        for ticker in tickers_to_remove:
            # Remove all article links first
            db.query(ArticleTicker).filter(
                ArticleTicker.ticker == ticker.symbol
            ).delete()

            # Remove the ticker
            db.delete(ticker)
            removed_count += 1
            print(f"Removed {ticker.symbol} - {ticker.name}")

        db.commit()
        print(f"\nRemoved {removed_count} problematic tickers")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Remove problematic tickers that are common English words"
    )
    parser.add_argument(
        "--apply", action="store_true", help="Apply changes (default is dry run)"
    )

    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)

    remove_problematic_tickers(dry_run=not args.apply)
