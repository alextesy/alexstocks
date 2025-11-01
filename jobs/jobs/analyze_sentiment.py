#!/usr/bin/env python3
"""Dedicated sentiment analysis job for articles without sentiment data."""

import argparse
import logging
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime, timedelta
from typing import Any

from dotenv import load_dotenv
from sqlalchemy import select, update
from sqlalchemy.orm import Session
from tqdm import tqdm

# Load .env BEFORE importing app modules that use settings
load_dotenv()

# Add project root to path
sys.path.append(".")

from app.db.models import Article  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.services.llm_sentiment import get_llm_sentiment_service  # noqa: E402
from app.services.sentiment import get_sentiment_service_hybrid  # noqa: E402
from .slack_wrapper import run_with_slack  # noqa: E402

logger = logging.getLogger(__name__)


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


def get_articles_without_sentiment(
    db: Session,
    limit: int | None = None,
    source_filter: str | None = None,
    hours_back: int | None = None,
) -> list[Article]:
    """Get articles that don't have sentiment analysis yet.

    Args:
        db: Database session
        limit: Maximum number of articles to retrieve
        source_filter: Filter by source (e.g., 'reddit')
        hours_back: Only get articles from the last N hours

    Returns:
        List of Article objects without sentiment
    """
    query = select(Article).where(Article.sentiment.is_(None))

    # Add source filter if specified
    if source_filter:
        if source_filter == "reddit":
            query = query.where(Article.source.like("%reddit%"))
        else:
            query = query.where(Article.source == source_filter)

    # Add time filter if specified
    if hours_back:
        cutoff_time = datetime.now(UTC) - timedelta(hours=hours_back)
        query = query.where(Article.created_at >= cutoff_time)

    # Order by creation time (newest first)
    query = query.order_by(Article.created_at.desc())

    # Apply limit if specified
    if limit:
        query = query.limit(limit)

    return list(db.execute(query).scalars().all())


def analyze_single_article_sentiment(
    article: Article, use_llm_only: bool = False
) -> tuple[int, float | None]:
    """Analyze sentiment for a single article.

    Args:
        article: Article to analyze
        use_llm_only: If True, use LLM only (no fallback)

    Returns:
        Tuple of (article_id, sentiment_score)
    """
    try:
        if use_llm_only:
            sentiment_service = get_llm_sentiment_service()
        else:
            # Use hybrid service (LLM by default with VADER fallback)
            sentiment_service = get_sentiment_service_hybrid()

        # Prepare text for sentiment analysis
        # For Reddit comments, use only the text. For posts, use title + text
        if article.source == "reddit_comment":
            sentiment_text = article.text or ""
        else:
            sentiment_text = article.title
            if article.text:
                sentiment_text += " " + article.text

        # Skip empty content
        if not sentiment_text.strip():
            logger.warning(f"Empty content for article {article.id}, skipping")
            return article.id, None

        # Analyze sentiment
        sentiment_score = sentiment_service.analyze_sentiment(sentiment_text)

        logger.debug(
            f"Analyzed sentiment for {article.source} {article.id}: {sentiment_score:.3f}"
        )
        return article.id, sentiment_score

    except Exception as e:
        logger.warning(f"Failed to analyze sentiment for article {article.id}: {e}")
        return article.id, None


def analyze_articles_parallel(
    articles: list[Article],
    max_workers: int = 4,
    batch_size: int = 100,
    use_llm_only: bool = False,
) -> int:
    """Analyze sentiment for multiple articles in parallel.

    Args:
        articles: List of articles to analyze
        max_workers: Maximum number of parallel workers
        batch_size: Batch size for database updates

    Returns:
        Number of articles successfully processed
    """
    if not articles:
        logger.info("No articles to process")
        return 0

    logger.info(
        f"Processing {len(articles)} articles with {max_workers} parallel workers"
    )

    # Process articles in parallel
    sentiment_results = []

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all tasks
        future_to_article = {
            executor.submit(
                analyze_single_article_sentiment, article, use_llm_only
            ): article
            for article in articles
        }

        # Collect results with progress bar
        with tqdm(
            total=len(articles), desc="Analyzing sentiment", unit="articles"
        ) as pbar:
            for future in as_completed(future_to_article):
                article_id, sentiment_score = future.result()
                sentiment_results.append((article_id, sentiment_score))

                # Update progress bar
                pbar.update(1)

    # Update database in batches
    db = SessionLocal()
    try:
        successful_updates = 0

        with tqdm(
            total=len(sentiment_results), desc="Updating database", unit="articles"
        ) as pbar:
            for i in range(0, len(sentiment_results), batch_size):
                batch = sentiment_results[i : i + batch_size]

                try:
                    for article_id, sentiment_score in batch:
                        if sentiment_score is not None:
                            db.execute(
                                update(Article)
                                .where(Article.id == article_id)
                                .values(sentiment=sentiment_score)
                            )
                            successful_updates += 1

                    db.commit()
                    pbar.update(len(batch))

                except Exception as e:
                    logger.error(f"Error updating batch: {e}")
                    db.rollback()

        logger.info(f"Successfully updated sentiment for {successful_updates} articles")
        return successful_updates

    except Exception as e:
        logger.error(f"Database error: {e}")
        db.rollback()
        return 0
    finally:
        db.close()


def run_sentiment_analysis(
    max_articles: int | None = None,
    source_filter: str | None = None,
    hours_back: int | None = None,
    max_workers: int = 4,
    batch_size: int = 100,
    use_llm_only: bool = False,
    verbose: bool = False,
) -> dict[str, Any]:
    """Run sentiment analysis on articles without sentiment data.

    Args:
        max_articles: Maximum number of articles to process
        source_filter: Filter by source (e.g., 'reddit')
        hours_back: Only process articles from the last N hours
        max_workers: Maximum number of parallel workers
        batch_size: Batch size for database updates
        verbose: Enable verbose logging

    Returns:
        Dictionary with stats for Slack notification
    """
    setup_logging(verbose)

    logger.info("Starting sentiment analysis job")

    if source_filter:
        logger.info(f"Filtering by source: {source_filter}")
    if hours_back:
        logger.info(f"Processing articles from last {hours_back} hours")
    if max_articles:
        logger.info(f"Limited to {max_articles} articles")

    # Get database session
    db = SessionLocal()
    try:
        # Get articles without sentiment
        logger.info("Querying articles without sentiment analysis...")
        articles = get_articles_without_sentiment(
            db, limit=max_articles, source_filter=source_filter, hours_back=hours_back
        )

        if not articles:
            logger.info("No articles found without sentiment analysis")
            return {
                "processed": 0,
                "success": 0,
                "failed": 0,
            }

        logger.info(f"Found {len(articles)} articles to process")

        # Analyze sentiment in parallel
        successful_count = analyze_articles_parallel(
            articles,
            max_workers=max_workers,
            batch_size=batch_size,
            use_llm_only=use_llm_only,
        )

        failed_count = len(articles) - successful_count

        logger.info(
            f"Sentiment analysis complete: {successful_count}/{len(articles)} articles processed successfully"
        )

        # Return stats for Slack notification
        return {
            "processed": len(articles),
            "success": successful_count,
            "failed": failed_count,
        }

    except Exception as e:
        logger.error(f"Error during sentiment analysis: {e}")
        raise
    finally:
        db.close()


def main() -> None:
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Analyze sentiment for articles without sentiment data"
    )
    parser.add_argument(
        "--max-articles",
        type=int,
        default=None,
        help="Maximum number of articles to process (default: all)",
    )
    parser.add_argument(
        "--source",
        type=str,
        default=None,
        help="Filter by source type (e.g., 'reddit')",
    )
    parser.add_argument(
        "--hours-back",
        type=int,
        default=None,
        help="Only process articles from the last N hours",
    )
    parser.add_argument(
        "--max-workers",
        type=int,
        default=4,
        help="Maximum number of parallel workers (default: 4)",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=100,
        help="Batch size for database updates (default: 100)",
    )
    parser.add_argument(
        "--llm-only",
        action="store_true",
        help="Use LLM sentiment only (no VADER fallback)",
    )
    parser.add_argument("--verbose", action="store_true", help="Enable verbose logging")

    args = parser.parse_args()

    def run_job():
        return run_sentiment_analysis(
            max_articles=args.max_articles,
            source_filter=args.source,
            hours_back=args.hours_back,
            max_workers=args.max_workers,
            batch_size=args.batch_size,
            use_llm_only=args.llm_only,
            verbose=args.verbose,
        )

    run_with_slack(
        job_name="analyze_sentiment",
        job_func=run_job,
        metadata={
            "source": args.source or "all",
            "max_workers": args.max_workers,
            "max_articles": args.max_articles or "unlimited",
        },
    )


if __name__ == "__main__":
    main()
