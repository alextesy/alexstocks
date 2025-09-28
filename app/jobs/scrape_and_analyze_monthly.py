#!/usr/bin/env python3
"""Combined job that scrapes monthly Reddit discussions and then analyzes sentiment."""

import argparse
import logging
import sys
import subprocess
from typing import List, Optional

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


def run_monthly_scraping(
    subreddit: str = "wallstreetbets",
    days_back: int = 30,
    max_threads: int = 10,
    max_replace_more: int = 10,
    max_workers: int = 5,
    skip_existing: bool = True,
    verbose: bool = False
) -> bool:
    """Run monthly Reddit discussion scraping.
    
    Args:
        subreddit: Subreddit to scrape
        days_back: Number of days to look back
        max_threads: Maximum number of threads to process
        max_replace_more: Maximum "more comments" to expand per thread
        max_workers: Maximum number of workers for ticker linking
        skip_existing: Skip comments already in database
        verbose: Enable verbose logging
        
    Returns:
        True if successful, False otherwise
    """
    logger.info("Starting monthly Reddit discussion scraping...")
    
    try:
        # Build command
        cmd = [
            "uv", "run", "python", "app/jobs/scrape_monthly_discussions.py",
            "--subreddit", subreddit,
            "--days-back", str(days_back),
            "--max-threads", str(max_threads),
            "--max-replace-more", str(max_replace_more),
            "--workers", str(max_workers)
        ]
        
        if not skip_existing:
            cmd.append("--include-existing")
        
        if verbose:
            cmd.append("--verbose")
        
        # Run the command
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode == 0:
            logger.info("Monthly Reddit scraping completed successfully")
            if verbose:
                logger.debug(f"Scraping output: {result.stdout}")
            return True
        else:
            logger.error(f"Monthly Reddit scraping failed with return code {result.returncode}")
            logger.error(f"Error output: {result.stderr}")
            return False
            
    except Exception as e:
        logger.error(f"Error running monthly Reddit scraping: {e}")
        return False


def run_sentiment_analysis(
    max_articles: Optional[int] = None,
    source_filter: str = "reddit",
    hours_back: int = 720,  # 30 days in hours
    max_workers: int = 6,
    verbose: bool = False
) -> bool:
    """Run sentiment analysis on newly scraped data.
    
    Args:
        max_articles: Max articles to process
        source_filter: Source filter
        hours_back: Only process articles from last N hours (default: 720 = 30 days)
        max_workers: Max workers for sentiment analysis
        verbose: Enable verbose logging
        
    Returns:
        True if successful, False otherwise
    """
    logger.info(f"Starting sentiment analysis for {source_filter} articles from last {hours_back} hours...")
    
    try:
        # Build command
        cmd = [
            "uv", "run", "python", "app/jobs/analyze_sentiment.py",
            "--source", source_filter,
            "--hours-back", str(hours_back),
            "--max-workers", str(max_workers)
        ]
        
        if max_articles:
            cmd.extend(["--max-articles", str(max_articles)])
        
        if verbose:
            cmd.append("--verbose")
        
        # Run the command
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode == 0:
            logger.info("Sentiment analysis completed successfully")
            if verbose:
                logger.debug(f"Sentiment output: {result.stdout}")
            return True
        else:
            logger.error(f"Sentiment analysis failed with return code {result.returncode}")
            logger.error(f"Error output: {result.stderr}")
            return False
            
    except Exception as e:
        logger.error(f"Error running sentiment analysis: {e}")
        return False


def run_combined_monthly_job(
    subreddit: str = "wallstreetbets",
    days_back: int = 30,
    max_threads: int = 10,
    max_replace_more: int = 10,
    scraping_workers: int = 5,
    sentiment_workers: int = 6,
    hours_back: int = 720,  # 30 days in hours
    skip_existing: bool = True,
    verbose: bool = False
) -> None:
    """Run combined monthly scraping and sentiment analysis job.
    
    Args:
        subreddit: Subreddit to scrape
        days_back: Number of days to look back for scraping
        max_threads: Maximum number of threads to process
        max_replace_more: Maximum "more comments" to expand per thread
        scraping_workers: Workers for scraping
        sentiment_workers: Workers for sentiment analysis
        hours_back: Hours back for sentiment analysis (default: 720 = 30 days)
        skip_existing: Skip comments already in database
        verbose: Enable verbose logging
    """
    setup_logging(verbose)
    
    logger.info(f"Starting combined monthly scraping and sentiment analysis job for r/{subreddit}")
    logger.info(f"Looking back {days_back} days, processing up to {max_threads} threads")
    
    # Step 1: Run monthly scraping
    scraping_success = run_monthly_scraping(
        subreddit=subreddit,
        days_back=days_back,
        max_threads=max_threads,
        max_replace_more=max_replace_more,
        max_workers=scraping_workers,
        skip_existing=skip_existing,
        verbose=verbose
    )
    
    if not scraping_success:
        logger.error("Monthly scraping failed, skipping sentiment analysis")
        return
    
    # Step 2: Run sentiment analysis
    sentiment_success = run_sentiment_analysis(
        source_filter="reddit",
        hours_back=hours_back,
        max_workers=sentiment_workers,
        verbose=verbose
    )
    
    if sentiment_success:
        logger.info("✅ Combined monthly job completed successfully!")
        logger.info(f"📊 Processed {days_back} days of r/{subreddit} daily discussions")
        logger.info(f"🧠 Analyzed sentiment for articles from the last {hours_back} hours")
    else:
        logger.error("❌ Sentiment analysis failed")


def main() -> None:
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(description="Combined monthly Reddit scraping and sentiment analysis job")
    
    parser.add_argument(
        "--subreddit",
        type=str,
        default="wallstreetbets",
        help="Subreddit to scrape (default: wallstreetbets)",
    )
    parser.add_argument(
        "--days-back",
        type=int,
        default=30,
        help="Number of days to look back for scraping (default: 30)",
    )
    parser.add_argument(
        "--max-threads",
        type=int,
        default=10,
        help="Maximum number of threads to process (default: 10)",
    )
    parser.add_argument(
        "--max-replace-more",
        type=int,
        default=10,
        help="Maximum 'more comments' to expand per thread (default: 10)",
    )
    parser.add_argument(
        "--scraping-workers",
        type=int,
        default=5,
        help="Workers for scraping (default: 5)",
    )
    parser.add_argument(
        "--sentiment-workers",
        type=int,
        default=6,
        help="Workers for sentiment analysis (default: 6)",
    )
    parser.add_argument(
        "--hours-back",
        type=int,
        default=720,
        help="Hours back for sentiment analysis (default: 720 = 30 days)",
    )
    parser.add_argument(
        "--include-existing",
        action="store_true",
        help="Include comments already in database (default: skip existing)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose logging",
    )
    
    args = parser.parse_args()
    
    try:
        run_combined_monthly_job(
            subreddit=args.subreddit,
            days_back=args.days_back,
            max_threads=args.max_threads,
            max_replace_more=args.max_replace_more,
            scraping_workers=args.scraping_workers,
            sentiment_workers=args.sentiment_workers,
            hours_back=args.hours_back,
            skip_existing=not args.include_existing,
            verbose=args.verbose
        )
    except KeyboardInterrupt:
        logger.info("Job interrupted by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
