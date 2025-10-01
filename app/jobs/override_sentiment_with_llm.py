#!/usr/bin/env python3
"""Override all existing sentiment analysis with LLM sentiment."""

import argparse
import logging
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime, timedelta
from typing import List, Optional

from sqlalchemy import select, update, and_
from sqlalchemy.orm import Session
from tqdm import tqdm

from app.db.models import Article
from app.db.session import SessionLocal
from app.services.llm_sentiment import get_llm_sentiment_service

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


def get_articles_for_llm_override(
    db: Session, 
    limit: Optional[int] = None,
    source_filter: Optional[str] = None,
    hours_back: Optional[int] = None,
    force_all: bool = False
) -> List[Article]:
    """Get articles to override with LLM sentiment.

    Args:
        db: Database session
        limit: Maximum number of articles to retrieve
        source_filter: Filter by source (e.g., 'reddit')
        hours_back: Only get articles from the last N hours
        force_all: If True, override all articles. If False, only override non-LLM sentiment

    Returns:
        List of Article objects to process
    """
    if force_all:
        # Override all articles regardless of existing sentiment
        query = select(Article)
        logger.info("Selecting ALL articles for LLM sentiment override")
    else:
        # Only override articles that don't have LLM sentiment yet
        # (either no sentiment or VADER sentiment)
        query = select(Article).where(
            Article.sentiment.is_(None)
        )
        logger.info("Selecting articles without sentiment for LLM analysis")
    
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


def analyze_single_article_llm(article: Article) -> tuple[int, Optional[float]]:
    """Analyze sentiment for a single article using LLM only.
    
    Args:
        article: Article to analyze
        
    Returns:
        Tuple of (article_id, sentiment_score)
    """
    try:
        # Force LLM sentiment service (no fallback to VADER)
        llm_service = get_llm_sentiment_service()
        
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
        
        # Analyze sentiment with LLM
        sentiment_score = llm_service.analyze_sentiment(sentiment_text)
        
        logger.debug(f"LLM sentiment for {article.source} {article.id}: {sentiment_score:.3f}")
        return article.id, sentiment_score
        
    except Exception as e:
        logger.warning(f"Failed LLM sentiment analysis for article {article.id}: {e}")
        return article.id, None


def override_articles_parallel(
    articles: List[Article], 
    max_workers: int = 4,
    batch_size: int = 100
) -> int:
    """Override sentiment for multiple articles with LLM in parallel.
    
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
    
    logger.info(f"Overriding sentiment for {len(articles)} articles with LLM using {max_workers} parallel workers")
    
    # Process articles in parallel
    sentiment_results = []
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all tasks
        future_to_article = {
            executor.submit(analyze_single_article_llm, article): article 
            for article in articles
        }
        
        # Collect results with progress bar
        with tqdm(total=len(articles), desc="LLM sentiment analysis", unit="articles") as pbar:
            for future in as_completed(future_to_article):
                article_id, sentiment_score = future.result()
                sentiment_results.append((article_id, sentiment_score))
                
                # Update progress bar
                pbar.update(1)
    
    # Update database in batches
    db = SessionLocal()
    try:
        successful_updates = 0
        
        with tqdm(total=len(sentiment_results), desc="Updating database", unit="articles") as pbar:
            for i in range(0, len(sentiment_results), batch_size):
                batch = sentiment_results[i:i + batch_size]
                
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
        
        logger.info(f"Successfully updated LLM sentiment for {successful_updates} articles")
        return successful_updates
        
    except Exception as e:
        logger.error(f"Database error: {e}")
        db.rollback()
        return 0
    finally:
        db.close()


def run_llm_sentiment_override(
    max_articles: Optional[int] = None,
    source_filter: Optional[str] = None,
    hours_back: Optional[int] = None,
    force_all: bool = False,
    max_workers: int = 6,
    batch_size: int = 100,
    verbose: bool = False
) -> None:
    """Override existing sentiment analysis with LLM sentiment.

    Args:
        max_articles: Maximum number of articles to process
        source_filter: Filter by source (e.g., 'reddit')
        hours_back: Only process articles from the last N hours
        force_all: Override ALL articles, not just those without sentiment
        max_workers: Maximum number of parallel workers
        batch_size: Batch size for database updates
        verbose: Enable verbose logging
    """
    setup_logging(verbose)
    
    if force_all:
        logger.info("🔄 Starting LLM sentiment override for ALL articles")
        logger.warning("⚠️  This will replace ALL existing sentiment data with LLM sentiment")
    else:
        logger.info("🔄 Starting LLM sentiment analysis for articles without sentiment")
    
    if source_filter:
        logger.info(f"Filtering by source: {source_filter}")
    if hours_back:
        logger.info(f"Processing articles from last {hours_back} hours")
    if max_articles:
        logger.info(f"Limited to {max_articles} articles")
    
    # Get database session
    db = SessionLocal()
    try:
        # Get articles for LLM override
        logger.info("Querying articles for LLM sentiment override...")
        articles = get_articles_for_llm_override(
            db, 
            limit=max_articles,
            source_filter=source_filter,
            hours_back=hours_back,
            force_all=force_all
        )
        
        if not articles:
            logger.info("No articles found for LLM sentiment override")
            return
        
        logger.info(f"Found {len(articles)} articles to process with LLM sentiment")
        
        # Confirm for force_all mode
        if force_all and len(articles) > 100:
            logger.warning(f"⚠️  About to override sentiment for {len(articles)} articles")
            logger.warning("⚠️  This will replace all existing sentiment data with LLM sentiment")
            response = input("Continue? (yes/no): ")
            if response.lower() not in ['yes', 'y']:
                logger.info("Operation cancelled by user")
                return
        
        # Override sentiment with LLM
        successful_count = override_articles_parallel(
            articles, 
            max_workers=max_workers,
            batch_size=batch_size
        )
        
        logger.info(f"✅ LLM sentiment override complete: {successful_count}/{len(articles)} articles processed successfully")
        
        if force_all:
            logger.info("🎯 All articles now use LLM sentiment analysis (FinBERT)")
        
    except Exception as e:
        logger.error(f"Error during LLM sentiment override: {e}")
    finally:
        db.close()


def main() -> None:
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(description="Override existing sentiment with LLM sentiment")
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
        "--force-all",
        action="store_true",
        help="Override ALL articles (including those with existing sentiment)",
    )
    parser.add_argument(
        "--max-workers",
        type=int,
        default=6,
        help="Maximum number of parallel workers (default: 6)",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=100,
        help="Batch size for database updates (default: 100)",
    )
    parser.add_argument("--verbose", action="store_true", help="Enable verbose logging")
    
    args = parser.parse_args()
    
    try:
        run_llm_sentiment_override(
            max_articles=args.max_articles,
            source_filter=args.source,
            hours_back=args.hours_back,
            force_all=args.force_all,
            max_workers=args.max_workers,
            batch_size=args.batch_size,
            verbose=args.verbose,
        )
    except KeyboardInterrupt:
        logger.info("LLM sentiment override interrupted by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
