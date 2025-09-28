#!/usr/bin/env python3
"""Script to add sentiment analysis to existing articles in the database."""

import logging
import sys
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.db.models import Article
from app.db.session import SessionLocal
from app.services.sentiment import get_sentiment_service_hybrid

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


def add_sentiment_to_articles(
    batch_size: int = 100, 
    max_articles: int | None = None,
    verbose: bool = False
) -> None:
    """Add sentiment analysis to existing articles.

    Args:
        batch_size: Number of articles to process in each batch
        max_articles: Maximum number of articles to process (None for all)
        verbose: Enable verbose logging
    """
    setup_logging(verbose)
    
    logger.info("Starting sentiment analysis for existing articles")
    
    # Get sentiment service
    sentiment_service = get_sentiment_service_hybrid()
    
    # Get database session
    db = SessionLocal()
    try:
        # Get articles without sentiment
        query = select(Article).where(Article.sentiment.is_(None))
        if max_articles:
            query = query.limit(max_articles)
        
        articles = db.execute(query).scalars().all()
        total_articles = len(articles)
        
        if total_articles == 0:
            logger.info("No articles found without sentiment analysis")
            return
        
        logger.info(f"Found {total_articles} articles to process")
        
        processed = 0
        successful = 0
        failed = 0
        
        # Process articles in batches
        for i in range(0, total_articles, batch_size):
            batch = articles[i:i + batch_size]
            logger.info(f"Processing batch {i//batch_size + 1}: articles {i+1}-{min(i+batch_size, total_articles)}")
            
            for article in batch:
                try:
                    # Prepare text for sentiment analysis
                    # For Reddit comments, use only the text. For posts, use title + text
                    if article.source == 'reddit_comment':
                        sentiment_text = article.text or ""
                    else:
                        sentiment_text = article.title
                        if article.text:
                            sentiment_text += " " + article.text
                    
                    # Analyze sentiment
                    sentiment_score = sentiment_service.analyze_sentiment(sentiment_text)
                    
                    # Update article with sentiment
                    db.execute(
                        update(Article)
                        .where(Article.id == article.id)
                        .values(sentiment=sentiment_score)
                    )
                    
                    successful += 1
                    if verbose:
                        logger.debug(f"Article {article.id}: sentiment={sentiment_score:.3f}")
                        
                except Exception as e:
                    logger.warning(f"Failed to analyze sentiment for article {article.id}: {e}")
                    failed += 1
                
                processed += 1
            
            # Commit batch
            try:
                db.commit()
                logger.info(f"Batch committed: {successful} successful, {failed} failed")
            except Exception as e:
                logger.error(f"Error committing batch: {e}")
                db.rollback()
                failed += batch_size
                successful -= batch_size
        
        logger.info(f"Sentiment analysis complete: {successful} successful, {failed} failed out of {processed} total")
        
    except Exception as e:
        logger.error(f"Unexpected error during sentiment analysis: {e}")
        db.rollback()
    finally:
        db.close()


def main() -> None:
    """Main CLI entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Add sentiment analysis to existing articles")
    parser.add_argument(
        "--batch-size",
        type=int,
        default=100,
        help="Number of articles to process in each batch (default: 100)",
    )
    parser.add_argument(
        "--max-articles",
        type=int,
        default=None,
        help="Maximum number of articles to process (default: all)",
    )
    parser.add_argument("--verbose", action="store_true", help="Enable verbose logging")
    
    args = parser.parse_args()
    
    try:
        add_sentiment_to_articles(
            batch_size=args.batch_size,
            max_articles=args.max_articles,
            verbose=args.verbose,
        )
    except KeyboardInterrupt:
        logger.info("Sentiment analysis interrupted by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
