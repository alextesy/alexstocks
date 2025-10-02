"""
CLI interface for production Reddit scraper.

Usage:
  # Incremental mode (for cron - 15min runs)
  python -m ingest.reddit_scraper_cli --mode incremental

  # Backfill mode (historical data)
  python -m ingest.reddit_scraper_cli --mode backfill --start 2025-09-01 --end 2025-09-30

  # Status check
  python -m ingest.reddit_scraper_cli --mode status
"""

import argparse
import logging
import sys
from datetime import UTC, datetime

from dotenv import load_dotenv

from ingest.reddit_discussion_scraper import get_reddit_credentials
from ingest.reddit_scraper import RedditScraper

load_dotenv()

logger = logging.getLogger(__name__)


def setup_logging(verbose: bool = False) -> None:
    """Setup structured logging."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )


def run_incremental(
    subreddit: str = "wallstreetbets",
    max_threads: int = 3,
    max_replace_more: int = 32,
    verbose: bool = False,
) -> None:
    """
    Run incremental scraping (for 15-min cron jobs).

    Args:
        subreddit: Subreddit to scrape
        max_threads: Max threads to process
        max_replace_more: Max "more comments" expansion
        verbose: Enable verbose logging
    """
    setup_logging(verbose)
    logger.info(f"🚀 Starting INCREMENTAL scraping for r/{subreddit}")

    try:
        # Get credentials
        client_id, client_secret, user_agent = get_reddit_credentials()
    except ValueError as e:
        logger.error(f"❌ Missing credentials: {e}")
        sys.exit(1)

    try:
        # Initialize scraper
        scraper = RedditScraper()
        scraper.initialize_reddit(client_id, client_secret, user_agent)

        # Run incremental scrape
        stats = scraper.scrape_incremental(
            subreddit_name=subreddit,
            max_threads=max_threads,
            max_replace_more=max_replace_more,
        )

        # Summary
        logger.info(f"\n{'=' * 60}")
        logger.info("📊 INCREMENTAL SCRAPE SUMMARY")
        logger.info(f"{'=' * 60}")
        logger.info(f"Threads processed:  {stats.threads_processed}")
        logger.info(f"Total comments:     {stats.total_comments}")
        logger.info(f"New comments:       {stats.new_comments}")
        logger.info(f"Articles created:   {stats.articles_created}")
        logger.info(f"Ticker links:       {stats.ticker_links}")
        logger.info(f"Batches saved:      {stats.batches_saved}")
        logger.info(f"Duration:           {stats.duration_ms}ms")
        logger.info(f"{'=' * 60}")

        print("\n✅ Incremental scraping completed successfully")

    except Exception as e:
        logger.error(f"❌ Fatal error: {e}", exc_info=True)
        sys.exit(1)


def run_backfill(
    subreddit: str,
    start_date: str,
    end_date: str,
    max_replace_more: int = 32,
    verbose: bool = False,
) -> None:
    """
    Run backfill for date range.

    Args:
        subreddit: Subreddit to scrape
        start_date: Start date (YYYY-MM-DD)
        end_date: End date (YYYY-MM-DD)
        max_replace_more: Max "more comments" expansion
        verbose: Enable verbose logging
    """
    setup_logging(verbose)

    # Parse dates
    try:
        start_dt = datetime.strptime(start_date, "%Y-%m-%d").replace(tzinfo=UTC)
        end_dt = datetime.strptime(end_date, "%Y-%m-%d").replace(tzinfo=UTC)
    except ValueError as e:
        logger.error(f"❌ Invalid date format (use YYYY-MM-DD): {e}")
        sys.exit(1)

    if start_dt > end_dt:
        logger.error("❌ Start date must be before or equal to end date")
        sys.exit(1)

    logger.info(f"🗓️  Starting BACKFILL for r/{subreddit}")
    logger.info(f"   Date range: {start_date} to {end_date}")

    try:
        # Get credentials
        client_id, client_secret, user_agent = get_reddit_credentials()
    except ValueError as e:
        logger.error(f"❌ Missing credentials: {e}")
        sys.exit(1)

    try:
        # Initialize scraper
        scraper = RedditScraper()
        scraper.initialize_reddit(client_id, client_secret, user_agent)

        # Run backfill
        stats = scraper.scrape_backfill(
            subreddit_name=subreddit,
            start_date=start_dt,
            end_date=end_dt,
            max_replace_more=max_replace_more,
        )

        # Summary
        logger.info(f"\n{'=' * 60}")
        logger.info("📊 BACKFILL SUMMARY")
        logger.info(f"{'=' * 60}")
        logger.info(f"Date range:         {start_date} to {end_date}")
        logger.info(f"Threads processed:  {stats.threads_processed}")
        logger.info(f"Total comments:     {stats.total_comments}")
        logger.info(f"New comments:       {stats.new_comments}")
        logger.info(f"Articles created:   {stats.articles_created}")
        logger.info(f"Ticker links:       {stats.ticker_links}")
        logger.info(f"Batches saved:      {stats.batches_saved}")
        logger.info(f"Duration:           {stats.duration_ms}ms")
        logger.info(f"{'=' * 60}")

        print("\n✅ Backfill completed successfully")

    except Exception as e:
        logger.error(f"❌ Fatal error: {e}", exc_info=True)
        sys.exit(1)


def show_status(subreddit: str = "wallstreetbets", verbose: bool = False) -> None:
    """
    Show scraping status.

    Args:
        subreddit: Subreddit to check
        verbose: Enable verbose logging
    """
    setup_logging(verbose)

    try:
        # Get credentials
        client_id, client_secret, user_agent = get_reddit_credentials()
    except ValueError as e:
        print(f"❌ Reddit credentials not configured: {e}")
        return

    try:
        # Use RedditScraper for status
        scraper = RedditScraper()
        scraper.initialize_reddit(client_id, client_secret, user_agent)

        status = scraper.get_scraping_status(subreddit, check_live_counts=True)

        if "error" in status:
            print(f"❌ Error: {status['error']}")
            return

        # Display status
        print(f"\n{'=' * 60}")
        print(f"📊 REDDIT SCRAPING STATUS - r/{subreddit}")
        print(f"{'=' * 60}")
        print(f"Total threads tracked:   {status['total_threads']}")
        print(f"Total comments scraped:  {status['total_comments_scraped']:,}")
        print(f"Live counts enabled:     {status['live_counts_enabled']}")

        if status["recent_threads"]:
            print(f"\n{'─' * 60}")
            print("📋 RECENT THREADS")
            print(f"{'─' * 60}")

            for i, thread in enumerate(status["recent_threads"][:5], 1):
                print(f"\n{i}. {thread['title']}")
                print(f"   Type:        {thread['type']}")
                print(
                    f"   Progress:    {thread['scraped_comments']:,} / {thread['total_comments']:,} "
                    f"({thread['completion_rate']})"
                )
                print(f"   Last scraped: {thread['last_scraped'] or 'Never'}")
                print(
                    f"   Complete:     {'✅ Yes' if thread['is_complete'] else '⏳ No'}"
                )

        print(f"\n{'=' * 60}\n")

    except Exception as e:
        print(f"❌ Error: {e}")
        if verbose:
            logger.error("Error details:", exc_info=True)


def main() -> None:
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Production Reddit Scraper CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Incremental scraping (for cron)
  python -m ingest.reddit_scraper_cli --mode incremental

  # Backfill historical data
  python -m ingest.reddit_scraper_cli --mode backfill --start 2025-09-01 --end 2025-09-30

  # Check status
  python -m ingest.reddit_scraper_cli --mode status

  # Verbose incremental
  python -m ingest.reddit_scraper_cli --mode incremental --verbose

  # Custom subreddit
  python -m ingest.reddit_scraper_cli --mode incremental --subreddit stocks
        """,
    )

    parser.add_argument(
        "--mode",
        type=str,
        required=True,
        choices=["incremental", "backfill", "status"],
        help="Scraping mode: incremental (15-min cron), backfill (historical), or status",
    )

    parser.add_argument(
        "--subreddit",
        type=str,
        default="wallstreetbets",
        help="Subreddit to scrape (default: wallstreetbets)",
    )

    parser.add_argument(
        "--start",
        type=str,
        help="Start date for backfill (YYYY-MM-DD, inclusive)",
    )

    parser.add_argument(
        "--end",
        type=str,
        help="End date for backfill (YYYY-MM-DD, inclusive)",
    )

    parser.add_argument(
        "--max-threads",
        type=int,
        default=3,
        help="Max threads to process in incremental mode (default: 3)",
    )

    parser.add_argument(
        "--max-replace-more",
        type=int,
        default=32,
        help="Max 'more comments' to expand (default: 32, use 0 for unlimited - slow!)",
    )

    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose logging",
    )

    args = parser.parse_args()

    # Validate backfill args
    if args.mode == "backfill":
        if not args.start or not args.end:
            parser.error("--mode backfill requires --start and --end dates")

    # Handle max_replace_more=0 as None (unlimited)
    max_replace_more = args.max_replace_more if args.max_replace_more > 0 else None

    # Route to appropriate handler
    if args.mode == "incremental":
        run_incremental(
            subreddit=args.subreddit,
            max_threads=args.max_threads,
            max_replace_more=max_replace_more,
            verbose=args.verbose,
        )
    elif args.mode == "backfill":
        run_backfill(
            subreddit=args.subreddit,
            start_date=args.start,
            end_date=args.end,
            max_replace_more=max_replace_more,
            verbose=args.verbose,
        )
    elif args.mode == "status":
        show_status(subreddit=args.subreddit, verbose=args.verbose)


if __name__ == "__main__":
    main()
