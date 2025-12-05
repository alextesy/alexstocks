"""Shared utilities for ticker selection across jobs."""

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.db.models import Article, ArticleTicker, Ticker, UserTickerFollow

logger = logging.getLogger(__name__)


def get_top_n_tickers(db: Session, n: int = 50, hours: int = 24) -> list[str]:
    """
    Get top N most active tickers by article count in the last N hours.

    Filters out ETFs automatically.

    Args:
        db: Database session
        n: Number of top tickers to return
        hours: Time window in hours

    Returns:
        List of ticker symbols
    """
    cutoff_time = datetime.now(UTC) - timedelta(hours=hours)

    top_tickers = (
        db.query(
            ArticleTicker.ticker,
            func.count(ArticleTicker.article_id).label("article_count"),
        )
        .join(Article, ArticleTicker.article_id == Article.id)
        .join(Ticker, Ticker.symbol == ArticleTicker.ticker)
        .filter(
            Article.published_at >= cutoff_time,
            or_(Ticker.name.is_(None), ~Ticker.name.ilike("%ETF%")),
        )
        .group_by(ArticleTicker.ticker)
        .order_by(func.count(ArticleTicker.article_id).desc())
        .limit(n)
        .all()
    )

    symbols = [ticker for ticker, count in top_tickers]
    logger.info(f"Top {n} tickers in last {hours}h: {symbols}")
    return symbols


def get_followed_tickers(db: Session) -> list[str]:
    """
    Get all user-followed tickers.

    Args:
        db: Database session

    Returns:
        List of unique ticker symbols that users follow
    """
    followed = (
        db.query(UserTickerFollow.ticker)
        .distinct()
        .join(Ticker, UserTickerFollow.ticker == Ticker.symbol)
        .all()
    )
    symbols = [ticker for (ticker,) in followed]
    logger.info(f"Found {len(symbols)} user-followed tickers")
    return symbols

