#!/usr/bin/env python3
"""Override existing sentiment analysis with the new dual model approach.

This script re-analyzes all articles using the new dual model strategy that
intelligently combines LLM (FinBERT) and VADER models to reduce neutral classifications.
"""

import argparse
import logging
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.orm import Session
from tqdm import tqdm

from app.db.models import Article
from app.db.session import SessionLocal
from app.services.sentiment import get_sentiment_service_hybrid

logger = logging.getLogger(__name__)


def setup_logging(verbose: bool = False) -> None:
    """Set up logging configuration."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )


def get_articles_for_dual_model_override(
    db: Session,
    limit: int | None = None,
    source_filter: str | None = None,
    hours_back: int | None = None,
    force_all: bool = False
) -> list[Article]:
    """Get articles to override with dual model sentiment.

    Args:
        db: Database session
        limit: Maximum number of articles to retrieve
        source_filter: Filter by source (e.g., 'reddit')
        hours_back: Only get articles from the last N hours
        force_all: If True, override all articles. If False, only override articles with sentiment

    Returns:
        List of Article objects to process
    """
    if force_all:
        # Override all articles regardless of existing sentiment
        query = select(Article)
        logger.info("Selecting ALL articles for dual model sentiment override")
    else:
        # Only override articles that have existing sentiment (any sentiment)
        query = select(Article).where(
            Article.sentiment.is_not(None)
        )
        logger.info("Selecting articles with existing sentiment for dual model re-analysis")

    # Add source filter if specified
    if source_filter:
        if source_filter == 'reddit':
            query = query.where(Article.source.like('%reddit%'))
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


def analyze_single_article_dual_model(article: Article) -> tuple[int, float | None]:
    """Analyze sentiment for a single article using dual model approach.

    Args:
        article: Article to analyze

    Returns:
        Tuple of (article_id, sentiment_score)
    """
    try:
        # Use the new dual model hybrid service
        dual_service = get_sentiment_service_hybrid()

        # Prepare text for sentiment analysis
        # For Reddit comments, use only the text. For posts, use title + text
        if article.source == 'reddit_comment':
            sentiment_text = article.text or ""
        else:
            sentiment_text = article.title
            if article.text:
                sentiment_text += " " + article.text

        # Skip empty content
        if not sentiment_text.strip():
            logger.warning(f"Empty content for article {article.id}, skipping")
            return article.id, None

        # Analyze sentiment with dual model approach
        sentiment_score = dual_service.analyze_sentiment(sentiment_text)

        logger.debug(f"Dual model sentiment for {article.source} {article.id}: {sentiment_score:.3f}")
        return article.id, sentiment_score

    except Exception as e:
        logger.warning(f"Failed dual model sentiment analysis for article {article.id}: {e}")
        return article.id, None


def override_articles_parallel(
    articles: list[Article],
    max_workers: int = 4,
    batch_size: int = 100
) -> int:
    """Process articles in parallel and update sentiment in the database.

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

    logger.info(f"Overriding sentiment for {len(articles)} articles with dual model using {max_workers} parallel workers")

    # Process articles in parallel
    sentiment_results = []

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all tasks
        future_to_article = {
            executor.submit(analyze_single_article_dual_model, article): article
            for article in articles
        }

        # Collect results with progress bar
        with tqdm(total=len(articles), desc="Dual model sentiment analysis", unit="articles") as pbar:
            for future in as_completed(future_to_article):
                article_id, sentiment_score = future.result()
                sentiment_results.append((article_id, sentiment_score))

                # Update progress bar
                pbar.update(1)

    # Update database in batches
    db = SessionLocal()
    try:
        successful_updates = 0

        with tqdm(total=len(sentiment_results), desc="Database updates", unit="articles") as pbar:
            # Process in batches
            for i in range(0, len(sentiment_results), batch_size):
                batch = sentiment_results[i:i + batch_size]

                for article_id, sentiment_score in batch:
                    if sentiment_score is not None:
                        try:
                            db.execute(
                                update(Article)
                                .where(Article.id == article_id)
                                .values(sentiment=sentiment_score)
                            )
                            successful_updates += 1
                        except Exception as e:
                            logger.warning(f"Failed to update article {article_id}: {e}")

                    pbar.update(1)

                # Commit batch
                try:
                    db.commit()
                    logger.debug(f"Committed batch of {len(batch)} updates")
                except Exception as e:
                    logger.error(f"Error committing batch: {e}")
                    db.rollback()

        logger.info(f"Successfully updated sentiment for {successful_updates} articles")
        return successful_updates

    finally:
        db.close()


def main():
    """Main function to run dual model sentiment override."""
    parser = argparse.ArgumentParser(
        description="Override sentiment analysis with dual model approach"
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="Maximum number of articles to process"
    )
    parser.add_argument(
        "--source",
        type=str,
        help="Filter by source (e.g., 'reddit')"
    )
    parser.add_argument(
        "--hours-back",
        type=int,
        help="Only process articles from the last N hours"
    )
    parser.add_argument(
        "--force-all",
        action="store_true",
        help="Override ALL articles, including those without sentiment"
    )
    parser.add_argument(
        "--max-workers",
        type=int,
        default=4,
        help="Maximum number of parallel workers (default: 4)"
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=100,
        help="Batch size for database updates (default: 100)"
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose logging"
    )

    args = parser.parse_args()

    # Set up logging
    setup_logging(args.verbose)

    logger.info("Starting dual model sentiment override process")
    logger.info(f"Configuration: limit={args.limit}, source={args.source}, "
                f"hours_back={args.hours_back}, force_all={args.force_all}")

    # Get database session
    db = SessionLocal()
    try:
        # Get articles to process
        articles = get_articles_for_dual_model_override(
            db=db,
            limit=args.limit,
            source_filter=args.source,
            hours_back=args.hours_back,
            force_all=args.force_all
        )

        if not articles:
            logger.info("No articles found matching criteria")
            return

        logger.info(f"Found {len(articles)} articles to process")

        # Process articles
        successful = override_articles_parallel(
            articles=articles,
            max_workers=args.max_workers,
            batch_size=args.batch_size
        )

        logger.info(f"Dual model sentiment override complete: {successful}/{len(articles)} articles processed successfully")

    except Exception as e:
        logger.error(f"Error during dual model sentiment override: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
