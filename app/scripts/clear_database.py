#!/usr/bin/env python3
"""Clear all articles and article-ticker relationships from database."""

import logging

from app.db.models import Article, ArticleTicker, Ticker
from app.db.session import SessionLocal

logger = logging.getLogger(__name__)


def clear_database():
    """Clear all articles and article-ticker relationships."""
    logging.basicConfig(level=logging.INFO)

    session = SessionLocal()

    try:
        # Get counts before clearing
        article_count = session.query(Article).count()
        article_ticker_count = session.query(ArticleTicker).count()
        ticker_count = session.query(Ticker).count()

        logger.info("Before clearing:")
        logger.info(f"  Articles: {article_count}")
        logger.info(f"  Article-Ticker relationships: {article_ticker_count}")
        logger.info(f"  Tickers: {ticker_count}")

        # Clear article-ticker relationships first (foreign key constraints)
        deleted_article_tickers = session.query(ArticleTicker).delete()
        logger.info(f"Deleted {deleted_article_tickers} article-ticker relationships")

        # Clear articles
        deleted_articles = session.query(Article).delete()
        logger.info(f"Deleted {deleted_articles} articles")

        # Commit changes
        session.commit()

        # Verify clearing
        remaining_articles = session.query(Article).count()
        remaining_article_tickers = session.query(ArticleTicker).count()
        remaining_tickers = session.query(Ticker).count()

        logger.info("After clearing:")
        logger.info(f"  Articles: {remaining_articles}")
        logger.info(f"  Article-Ticker relationships: {remaining_article_tickers}")
        logger.info(f"  Tickers: {remaining_tickers}")

        if remaining_articles == 0 and remaining_article_tickers == 0:
            logger.info("✅ Database successfully cleared!")
        else:
            logger.error("❌ Database clearing failed - some records remain")

    except Exception as e:
        logger.error(f"Error clearing database: {e}")
        session.rollback()
        raise
    finally:
        session.close()


if __name__ == "__main__":
    clear_database()
