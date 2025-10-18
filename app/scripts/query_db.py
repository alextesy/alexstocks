"""Database query utility script."""

import argparse
import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import desc, func

from app.db.models import Article, ArticleTicker, Ticker
from app.db.session import SessionLocal

logger = logging.getLogger(__name__)


def query_tickers(limit: int = 10) -> None:
    """Query all tickers."""
    db = SessionLocal()
    try:
        tickers = db.query(Ticker).limit(limit).all()
        print(f"\n=== TICKERS (showing {len(tickers)}) ===")
        for ticker in tickers:
            print(f"{ticker.symbol}: {ticker.name}")
    finally:
        db.close()


def query_articles_by_source() -> None:
    """Query articles grouped by source."""
    db = SessionLocal()
    try:
        sources = (
            db.query(Article.source, func.count(Article.id))
            .group_by(Article.source)
            .all()
        )
        print("\n=== ARTICLES BY SOURCE ===")
        for source, count in sources:
            print(f"{source}: {count} articles")
    finally:
        db.close()


def query_top_tickers(limit: int = 10) -> None:
    """Query top tickers by article count."""
    db = SessionLocal()
    try:
        top_tickers = (
            db.query(
                Ticker.symbol,
                Ticker.name,
                func.count(ArticleTicker.article_id).label("article_count"),
            )
            .outerjoin(ArticleTicker)
            .group_by(Ticker.symbol, Ticker.name)
            .order_by(desc("article_count"))
            .limit(limit)
            .all()
        )

        print(f"\n=== TOP {limit} TICKERS BY ARTICLE COUNT ===")
        for symbol, name, count in top_tickers:
            print(f"{symbol} ({name}): {count} articles")
    finally:
        db.close()


def query_recent_articles(limit: int = 10) -> None:
    """Query recent articles."""
    db = SessionLocal()
    try:
        recent = (
            db.query(Article).order_by(desc(Article.published_at)).limit(limit).all()
        )

        print(f"\n=== RECENT {limit} ARTICLES ===")
        for article in recent:
            print(
                f"{article.published_at.strftime('%Y-%m-%d %H:%M')} | {article.source} | {article.title[:80]}..."
            )
    finally:
        db.close()


def query_ticker_articles(ticker_symbol: str, limit: int = 10) -> None:
    """Query articles for a specific ticker."""
    db = SessionLocal()
    try:
        articles = (
            db.query(Article, ArticleTicker.confidence)
            .join(ArticleTicker, Article.id == ArticleTicker.article_id)
            .filter(ArticleTicker.ticker == ticker_symbol.upper())
            .order_by(desc(Article.published_at))
            .limit(limit)
            .all()
        )

        print(
            f"\n=== ARTICLES FOR {ticker_symbol.upper()} (showing {len(articles)}) ==="
        )
        for article, confidence in articles:
            print(
                f"{article.published_at.strftime('%Y-%m-%d %H:%M')} | {confidence:.2f} | {article.title[:80]}..."
            )
    finally:
        db.close()


def query_articles_by_date_range(days_back: int = 7) -> None:
    """Query articles from the last N days."""
    db = SessionLocal()
    try:
        cutoff_date = datetime.now(UTC) - timedelta(days=days_back)

        articles = (
            db.query(Article)
            .filter(Article.published_at >= cutoff_date)
            .order_by(desc(Article.published_at))
            .limit(20)
            .all()
        )

        print(
            f"\n=== ARTICLES FROM LAST {days_back} DAYS (showing {len(articles)}) ==="
        )
        for article in articles:
            print(
                f"{article.published_at.strftime('%Y-%m-%d %H:%M')} | {article.source} | {article.title[:80]}..."
            )
    finally:
        db.close()


def query_database_stats() -> None:
    """Query database statistics."""
    db = SessionLocal()
    try:
        print("\n=== DATABASE STATISTICS ===")

        # Total counts
        ticker_count = db.query(Ticker).count()
        article_count = db.query(Article).count()
        link_count = db.query(ArticleTicker).count()

        print(f"Total Tickers: {ticker_count}")
        print(f"Total Articles: {article_count}")
        print(f"Total Article-Ticker Links: {link_count}")

        # Articles by source
        sources = (
            db.query(Article.source, func.count(Article.id))
            .group_by(Article.source)
            .all()
        )
        print("\nArticles by Source:")
        for source, count in sources:
            print(f"  {source}: {count}")

        # Date range
        oldest = db.query(func.min(Article.published_at)).scalar()
        newest = db.query(func.max(Article.published_at)).scalar()
        print("\nDate Range:")
        print(f"  Oldest: {oldest}")
        print(f"  Newest: {newest}")

    finally:
        db.close()


def main() -> None:
    """Main function for database queries."""
    parser = argparse.ArgumentParser(description="Query AlexStocks database")
    parser.add_argument("--tickers", action="store_true", help="Show all tickers")
    parser.add_argument(
        "--sources", action="store_true", help="Show articles by source"
    )
    parser.add_argument(
        "--top-tickers",
        type=int,
        metavar="N",
        help="Show top N tickers by article count",
    )
    parser.add_argument(
        "--recent", type=int, metavar="N", help="Show N recent articles"
    )
    parser.add_argument(
        "--ticker", type=str, metavar="SYMBOL", help="Show articles for specific ticker"
    )
    parser.add_argument(
        "--days", type=int, metavar="N", help="Show articles from last N days"
    )
    parser.add_argument("--stats", action="store_true", help="Show database statistics")
    parser.add_argument("--all", action="store_true", help="Show all queries")

    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)

    if args.all or not any(vars(args).values()):
        # Show all if --all or no arguments
        query_database_stats()
        query_articles_by_source()
        query_top_tickers(10)
        query_recent_articles(5)
    else:
        if args.stats:
            query_database_stats()
        if args.sources:
            query_articles_by_source()
        if args.top_tickers:
            query_top_tickers(args.top_tickers)
        if args.recent:
            query_recent_articles(args.recent)
        if args.ticker:
            query_ticker_articles(args.ticker)
        if args.days:
            query_articles_by_date_range(args.days)
        if args.tickers:
            query_tickers()


if __name__ == "__main__":
    main()
