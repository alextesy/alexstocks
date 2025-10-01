"""Reddit data ingestion CLI script."""

import argparse
import logging
import os
import sys

from dotenv import load_dotenv
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import Article, ArticleTicker, Ticker
from app.db.session import SessionLocal

# Sentiment analysis is now handled separately
from ingest.linker import TickerLinker
from ingest.reddit_parser import RedditParser

# Load environment variables from .env file
load_dotenv()

logger = logging.getLogger(__name__)

# Default target subreddits
DEFAULT_SUBREDDITS = ["wallstreetbets", "stocks", "investing"]


def setup_logging(verbose: bool = False) -> None:
    """Setup logging configuration.

    Args:
        verbose: Enable verbose logging
    """
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )


def get_reddit_credentials() -> tuple[str, str, str]:
    """Get Reddit API credentials from environment variables.

    Returns:
        Tuple of (client_id, client_secret, user_agent)

    Raises:
        ValueError: If required environment variables are not set
    """
    client_id = os.getenv("REDDIT_CLIENT_ID")
    client_secret = os.getenv("REDDIT_CLIENT_SECRET")
    user_agent = os.getenv("REDDIT_USER_AGENT", "MarketPulse/1.0 by MarketPulseBot")

    if not client_id or not client_secret:
        raise ValueError(
            "Reddit API credentials not found. Please set REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET environment variables."
        )

    return client_id, client_secret, user_agent


def load_tickers(db: Session) -> list[Ticker]:
    """Load all tickers from database.

    Args:
        db: Database session

    Returns:
        List of Ticker models
    """
    result = db.execute(select(Ticker))
    return list(result.scalars().all())


def upsert_reddit_article(db: Session, article: Article) -> Article | None:
    """Upsert Reddit article with reddit_id uniqueness.

    Args:
        db: Database session
        article: Article model instance

    Returns:
        Existing or newly created Article instance
    """
    try:
        # Check if article with this reddit_id already exists
        existing = db.execute(
            select(Article).where(Article.reddit_id == article.reddit_id)
        ).scalar_one_or_none()

        if existing:
            logger.debug(f"Reddit article already exists: {article.reddit_id}")
            return existing

        # Add new article
        db.add(article)
        db.flush()  # Get the ID
        return article

    except IntegrityError as e:
        logger.warning(f"Integrity error for Reddit article {article.reddit_id}: {e}")
        db.rollback()
        return None
    except Exception as e:
        logger.error(f"Error upserting Reddit article {article.reddit_id}: {e}")
        db.rollback()
        return None


def save_article_tickers(
    db: Session, article: Article, article_tickers: list[ArticleTicker]
) -> None:
    """Save article-ticker relationships.

    Args:
        db: Database session
        article: Article model instance
        article_tickers: List of ArticleTicker relationships
    """
    try:
        # Deduplicate relationships by (article_id, ticker) pair
        unique_relationships = {}
        for article_ticker in article_tickers:
            article_ticker.article_id = article.id
            key = (article_ticker.article_id, article_ticker.ticker)
            if key not in unique_relationships:
                unique_relationships[key] = article_ticker

        # Add unique relationships only
        db.add_all(unique_relationships.values())

    except Exception as e:
        logger.error(f"Error saving article-ticker relationships: {e}")
        db.rollback()


def ingest_reddit_data(
    subreddits: list[str] | None = None,
    limit_per_subreddit: int = 100,
    time_filter: str = "day",
    verbose: bool = False,
    max_workers: int = 10,
) -> None:
    """Ingest Reddit data from specified subreddits.

    Args:
        subreddits: List of subreddit names (without r/). If None, uses default subreddits.
        limit_per_subreddit: Maximum number of posts per subreddit
        time_filter: Time filter ('hour', 'day', 'week', 'month', 'year', 'all')
        verbose: Enable verbose logging
        max_workers: Maximum number of concurrent workers (for future use)
    """
    setup_logging(verbose)

    if subreddits is None:
        subreddits = DEFAULT_SUBREDDITS

    logger.info(f"Starting Reddit ingestion from subreddits: {subreddits}")

    # Get Reddit credentials
    try:
        client_id, client_secret, user_agent = get_reddit_credentials()
    except ValueError as e:
        logger.error(f"Reddit credentials error: {e}")
        return

    # Get database session
    db = SessionLocal()
    try:
        # Load tickers
        logger.info("Loading tickers from database")
        tickers = load_tickers(db)
        if not tickers:
            logger.error("No tickers found in database. Run seed-tickers first.")
            return

        logger.info(f"Loaded {len(tickers)} tickers")

        # Initialize Reddit parser
        reddit_parser = RedditParser()
        reddit_parser.initialize_reddit(client_id, client_secret, user_agent)

        # Initialize ticker linker
        linker = TickerLinker(tickers, max_scraping_workers=max_workers)

        # Parse Reddit posts
        logger.info(f"Fetching posts from {len(subreddits)} subreddits")
        articles = reddit_parser.parse_multiple_subreddits(
            subreddits, limit_per_subreddit, time_filter
        )

        if not articles:
            logger.warning("No articles parsed from Reddit")
            return

        logger.info(f"Parsed {len(articles)} articles from Reddit")

        # Link articles to tickers
        logger.info("Linking articles to tickers")
        linked_articles = linker.link_articles_to_db(articles)

        # Save to database
        total_articles = 0
        total_links = 0

        for article, article_tickers in linked_articles:
            # Upsert article (without sentiment analysis)
            saved_article = upsert_reddit_article(db, article)
            if not saved_article:
                continue

            total_articles += 1

            # Save article-ticker relationships
            if article_tickers:
                save_article_tickers(db, saved_article, article_tickers)
                total_links += len(article_tickers)

        # Commit batch
        try:
            db.commit()
            logger.info(
                f"Saved {total_articles} Reddit articles with {total_links} ticker links"
            )
        except Exception as e:
            logger.error(f"Error committing batch: {e}")
            db.rollback()

        logger.info(
            f"Reddit ingestion complete: {total_articles} articles, {total_links} ticker links"
        )

    except Exception as e:
        logger.error(f"Unexpected error during Reddit ingestion: {e}")
        db.rollback()
    finally:
        db.close()


def main() -> None:
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(description="Reddit data ingestion CLI")
    parser.add_argument(
        "--subreddits",
        nargs="+",
        default=DEFAULT_SUBREDDITS,
        help=f"Subreddits to ingest from (default: {' '.join(DEFAULT_SUBREDDITS)})",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=100,
        help="Maximum number of posts per subreddit (default: 100)",
    )
    parser.add_argument(
        "--time-filter",
        choices=["hour", "day", "week", "month", "year", "all"],
        default="day",
        help="Time filter for posts (default: day)",
    )
    parser.add_argument("--verbose", action="store_true", help="Enable verbose logging")
    parser.add_argument(
        "--workers",
        type=int,
        default=10,
        help="Number of concurrent workers (default: 10)",
    )

    args = parser.parse_args()

    try:
        ingest_reddit_data(
            subreddits=args.subreddits,
            limit_per_subreddit=args.limit,
            time_filter=args.time_filter,
            verbose=args.verbose,
            max_workers=args.workers,
        )
    except KeyboardInterrupt:
        logger.info("Reddit ingestion interrupted by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
