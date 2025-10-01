#!/usr/bin/env python3
"""Combined job that scrapes Reddit data and then analyzes sentiment."""

import argparse
import logging
import subprocess
import sys

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


def run_reddit_scraping(
    subreddits: list[str] | None = None,
    limit_per_subreddit: int = 100,
    time_filter: str = "day",
    max_workers: int = 10,
    verbose: bool = False,
) -> bool:
    """Run Reddit scraping.

    Args:
        subreddits: List of subreddits to scrape
        limit_per_subreddit: Limit per subreddit
        time_filter: Time filter for posts
        max_workers: Max workers for scraping
        verbose: Enable verbose logging

    Returns:
        True if successful, False otherwise
    """
    logger.info("Starting Reddit scraping...")

    try:
        # Build command
        cmd = [
            "uv",
            "run",
            "python",
            "-m",
            "ingest.reddit",
            "--limit",
            str(limit_per_subreddit),
            "--time-filter",
            time_filter,
            "--workers",
            str(max_workers),
        ]

        if subreddits:
            cmd.extend(["--subreddits"] + subreddits)

        if verbose:
            cmd.append("--verbose")

        # Run the command
        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode == 0:
            logger.info("Reddit scraping completed successfully")
            if verbose:
                logger.debug(f"Scraping output: {result.stdout}")
            return True
        else:
            logger.error(f"Reddit scraping failed with return code {result.returncode}")
            logger.error(f"Error output: {result.stderr}")
            return False

    except Exception as e:
        logger.error(f"Error running Reddit scraping: {e}")
        return False


def run_incremental_scraping(
    subreddit: str = "wallstreetbets",
    max_threads: int = 3,
    max_comments_per_thread: int = 500,
    max_workers: int = 5,
    verbose: bool = False,
) -> bool:
    """Run incremental Reddit scraping.

    Args:
        subreddit: Subreddit to scrape
        max_threads: Max threads to process
        max_comments_per_thread: Max comments per thread
        max_workers: Max workers
        verbose: Enable verbose logging

    Returns:
        True if successful, False otherwise
    """
    logger.info(f"Starting incremental Reddit scraping for r/{subreddit}...")

    try:
        # Build command
        cmd = [
            "uv",
            "run",
            "python",
            "-m",
            "ingest.reddit_incremental",
            "scrape",
            "--subreddit",
            subreddit,
            "--max-threads",
            str(max_threads),
            "--max-comments-per-thread",
            str(max_comments_per_thread),
            "--workers",
            str(max_workers),
        ]

        if verbose:
            cmd.append("--verbose")

        # Run the command
        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode == 0:
            logger.info("Incremental Reddit scraping completed successfully")
            if verbose:
                logger.debug(f"Scraping output: {result.stdout}")
            return True
        else:
            logger.error(
                f"Incremental Reddit scraping failed with return code {result.returncode}"
            )
            logger.error(f"Error output: {result.stderr}")
            return False

    except Exception as e:
        logger.error(f"Error running incremental Reddit scraping: {e}")
        return False


def run_sentiment_analysis(
    max_articles: int | None = None,
    source_filter: str = "reddit",
    hours_back: int = 24,
    max_workers: int = 6,
    verbose: bool = False,
) -> bool:
    """Run sentiment analysis on newly scraped data.

    Args:
        max_articles: Max articles to process
        source_filter: Source filter
        hours_back: Only process articles from last N hours
        max_workers: Max workers for sentiment analysis
        verbose: Enable verbose logging

    Returns:
        True if successful, False otherwise
    """
    logger.info(
        f"Starting sentiment analysis for {source_filter} articles from last {hours_back} hours..."
    )

    try:
        # Build command
        cmd = [
            "uv",
            "run",
            "python",
            "app/jobs/analyze_sentiment.py",
            "--source",
            source_filter,
            "--hours-back",
            str(hours_back),
            "--max-workers",
            str(max_workers),
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
            logger.error(
                f"Sentiment analysis failed with return code {result.returncode}"
            )
            logger.error(f"Error output: {result.stderr}")
            return False

    except Exception as e:
        logger.error(f"Error running sentiment analysis: {e}")
        return False


def run_combined_job(
    job_type: str = "posts",
    subreddits: list[str] | None = None,
    subreddit: str = "wallstreetbets",
    limit_per_subreddit: int = 100,
    max_threads: int = 3,
    max_comments_per_thread: int = 500,
    scraping_workers: int = 10,
    sentiment_workers: int = 6,
    time_filter: str = "day",
    hours_back: int = 24,
    verbose: bool = False,
) -> None:
    """Run combined scraping and sentiment analysis job.

    Args:
        job_type: Type of job ('posts' or 'comments')
        subreddits: List of subreddits for posts scraping
        subreddit: Single subreddit for comments scraping
        limit_per_subreddit: Limit per subreddit for posts
        max_threads: Max threads for comments scraping
        max_comments_per_thread: Max comments per thread
        scraping_workers: Workers for scraping
        sentiment_workers: Workers for sentiment analysis
        time_filter: Time filter for posts
        hours_back: Hours back for sentiment analysis
        verbose: Enable verbose logging
    """
    setup_logging(verbose)

    logger.info(f"Starting combined {job_type} scraping and sentiment analysis job")

    # Step 1: Run scraping
    scraping_success = False

    if job_type == "posts":
        scraping_success = run_reddit_scraping(
            subreddits=subreddits,
            limit_per_subreddit=limit_per_subreddit,
            time_filter=time_filter,
            max_workers=scraping_workers,
            verbose=verbose,
        )
    elif job_type == "comments":
        scraping_success = run_incremental_scraping(
            subreddit=subreddit,
            max_threads=max_threads,
            max_comments_per_thread=max_comments_per_thread,
            max_workers=scraping_workers,
            verbose=verbose,
        )
    else:
        logger.error(f"Unknown job type: {job_type}")
        return

    if not scraping_success:
        logger.error("Scraping failed, skipping sentiment analysis")
        return

    # Step 2: Run sentiment analysis
    sentiment_success = run_sentiment_analysis(
        source_filter="reddit",
        hours_back=hours_back,
        max_workers=sentiment_workers,
        verbose=verbose,
    )

    if sentiment_success:
        logger.info("✅ Combined job completed successfully!")
    else:
        logger.error("❌ Sentiment analysis failed")


def main() -> None:
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Combined Reddit scraping and sentiment analysis job"
    )

    subparsers = parser.add_subparsers(dest="command", help="Job types")

    # Posts job
    posts_parser = subparsers.add_parser(
        "posts", help="Scrape Reddit posts and analyze sentiment"
    )
    posts_parser.add_argument(
        "--subreddits",
        nargs="+",
        default=["wallstreetbets", "stocks", "investing"],
        help="Subreddits to scrape",
    )
    posts_parser.add_argument(
        "--limit",
        type=int,
        default=100,
        help="Limit per subreddit (default: 100)",
    )
    posts_parser.add_argument(
        "--time-filter",
        choices=["hour", "day", "week", "month", "year", "all"],
        default="day",
        help="Time filter (default: day)",
    )
    posts_parser.add_argument(
        "--scraping-workers",
        type=int,
        default=10,
        help="Workers for scraping (default: 10)",
    )
    posts_parser.add_argument(
        "--sentiment-workers",
        type=int,
        default=6,
        help="Workers for sentiment analysis (default: 6)",
    )
    posts_parser.add_argument(
        "--verbose", action="store_true", help="Enable verbose logging"
    )

    # Comments job
    comments_parser = subparsers.add_parser(
        "comments", help="Scrape Reddit comments and analyze sentiment"
    )
    comments_parser.add_argument(
        "--subreddit",
        type=str,
        default="wallstreetbets",
        help="Subreddit to scrape (default: wallstreetbets)",
    )
    comments_parser.add_argument(
        "--max-threads",
        type=int,
        default=3,
        help="Max threads to process (default: 3)",
    )
    comments_parser.add_argument(
        "--max-comments-per-thread",
        type=int,
        default=500,
        help="Max comments per thread (default: 500)",
    )
    comments_parser.add_argument(
        "--scraping-workers",
        type=int,
        default=5,
        help="Workers for scraping (default: 5)",
    )
    comments_parser.add_argument(
        "--sentiment-workers",
        type=int,
        default=6,
        help="Workers for sentiment analysis (default: 6)",
    )
    comments_parser.add_argument(
        "--verbose", action="store_true", help="Enable verbose logging"
    )

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    try:
        if args.command == "posts":
            run_combined_job(
                job_type="posts",
                subreddits=args.subreddits,
                limit_per_subreddit=args.limit,
                time_filter=args.time_filter,
                scraping_workers=args.scraping_workers,
                sentiment_workers=args.sentiment_workers,
                verbose=args.verbose,
            )
        elif args.command == "comments":
            run_combined_job(
                job_type="comments",
                subreddit=args.subreddit,
                max_threads=args.max_threads,
                max_comments_per_thread=args.max_comments_per_thread,
                scraping_workers=args.scraping_workers,
                sentiment_workers=args.sentiment_workers,
                verbose=args.verbose,
            )
    except KeyboardInterrupt:
        logger.info("Job interrupted by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
