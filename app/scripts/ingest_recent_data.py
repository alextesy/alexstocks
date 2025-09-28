#!/usr/bin/env python3
"""Ingest recent GDELT data using improved ticker linking."""

import logging
import requests
from datetime import UTC, datetime, timedelta
from pathlib import Path

from app.db.models import Article, ArticleTicker, Ticker
from app.db.session import SessionLocal
from ingest.gdelt import ingest_gdelt_data
from ingest.parser import parse_gdelt_export_csv
from ingest.linker import TickerLinker

logger = logging.getLogger(__name__)


def ingest_recent_data(days_back: int = 1) -> None:
    """Ingest GDELT data from the last N days.
    
    Args:
        days_back: Number of days back to fetch data
    """
    logging.basicConfig(level=logging.INFO)
    
    # Calculate date range
    end_date = datetime.now(UTC)
    start_date = end_date - timedelta(days=days_back)
    
    logger.info(f"Ingesting GDELT data from {start_date.date()} to {end_date.date()}")
    
    # Get database session
    session = SessionLocal()
    
    try:
        # Get tickers from database
        tickers = session.query(Ticker).all()
        if not tickers:
            logger.error("No tickers found in database. Please seed tickers first.")
            return
        
        logger.info(f"Found {len(tickers)} tickers in database")
        
        # Create linker
        linker = TickerLinker(tickers)
        
        # Fetch GDELT data
        logger.info("Fetching GDELT data...")
        gdelt_data = fetch_gdelt_data(start_date, end_date)
        
        if not gdelt_data:
            logger.warning("No GDELT data found for the specified date range")
            return
        
        logger.info(f"Fetched {len(gdelt_data)} bytes of GDELT data")
        
        # Parse articles
        logger.info("Parsing GDELT data...")
        articles = parse_gdelt_export_csv(gdelt_data)
        
        if not articles:
            logger.warning("No articles parsed from GDELT data")
            return
        
        logger.info(f"Parsed {len(articles)} articles")
        
        # Link articles to tickers using improved system
        logger.info("Linking articles to tickers...")
        linking_results = linker.link_articles_to_db(articles)
        
        # Save to database
        logger.info("Saving to database...")
        saved_articles = 0
        saved_links = 0
        
        for article, article_tickers in linking_results:
            # Save article
            session.add(article)
            session.flush()  # Get the article ID
            
            # Save article-ticker relationships
            for article_ticker in article_tickers:
                article_ticker.article_id = article.id
                session.add(article_ticker)
                saved_links += 1
            
            saved_articles += 1
        
        # Commit all changes
        session.commit()
        
        # Log summary
        logger.info("="*60)
        logger.info("INGESTION SUMMARY")
        logger.info("="*60)
        logger.info(f"Date range: {start_date.date()} to {end_date.date()}")
        logger.info(f"Articles processed: {len(articles)}")
        logger.info(f"Articles saved: {saved_articles}")
        logger.info(f"Article-ticker links saved: {saved_links}")
        logger.info(f"Average links per article: {saved_links/saved_articles if saved_articles > 0 else 0:.2f}")
        
        # Show some examples
        if saved_links > 0:
            logger.info("\nSample article-ticker links:")
            sample_links = (
                session.query(Article.title, ArticleTicker.ticker, ArticleTicker.confidence)
                .join(ArticleTicker, Article.id == ArticleTicker.article_id)
                .order_by(ArticleTicker.confidence.desc())
                .limit(5)
                .all()
            )
            
            for title, ticker, confidence in sample_links:
                logger.info(f"  {ticker}: {confidence:.2f} - {title[:60]}...")
        
        logger.info("✅ Ingestion completed successfully!")
        
    except Exception as e:
        logger.error(f"Error during ingestion: {e}")
        session.rollback()
        raise
    finally:
        session.close()


def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Ingest recent GDELT data")
    parser.add_argument(
        "--days", 
        type=int, 
        default=1, 
        help="Number of days back to fetch data (default: 1)"
    )
    
    args = parser.parse_args()
    
    ingest_recent_data(args.days)


if __name__ == "__main__":
    main()
