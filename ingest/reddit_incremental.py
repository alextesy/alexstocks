"""CLI script for incremental Reddit discussion scraping (cron job)."""

import argparse
import logging
import sys

from dotenv import load_dotenv

from ingest.reddit import get_reddit_credentials
from ingest.reddit_incremental_scraper import RedditIncrementalScraper

# Load environment variables from .env file
load_dotenv()

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


def run_incremental_scrape(
    subreddit: str = "wallstreetbets",
    max_threads: int = 3,
    max_comments_per_thread: int = 500,
    max_workers: int = 5,
    verbose: bool = False,
) -> None:
    """Run incremental Reddit scraping.

    Args:
        subreddit: Subreddit to scrape
        max_threads: Maximum number of threads to process
        max_comments_per_thread: Maximum new comments per thread
        max_workers: Maximum number of workers for ticker linking
        verbose: Enable verbose logging
    """
    setup_logging(verbose)
    logger.info(f"Starting incremental Reddit scraping for r/{subreddit}")

    try:
        # Get Reddit credentials
        client_id, client_secret, user_agent = get_reddit_credentials()
    except ValueError as e:
        logger.error(f"Skipping Reddit scraping due to missing credentials: {e}")
        return

    try:
        # Initialize scraper
        scraper = RedditIncrementalScraper(max_scraping_workers=max_workers)
        scraper.initialize_reddit(client_id, client_secret, user_agent)

        # Run incremental scrape
        results = scraper.run_incremental_scrape(
            subreddit_name=subreddit,
            max_threads=max_threads,
            max_new_comments_per_thread=max_comments_per_thread,
        )

        if "error" in results:
            logger.error(f"Scraping failed: {results['error']}")
            sys.exit(1)

        # Log results
        logger.info("Incremental scraping completed successfully:")
        logger.info(f"  Threads processed: {results['threads_processed']}")
        logger.info(f"  New threads: {results['new_threads']}")
        logger.info(f"  New comments: {results['total_new_comments']}")
        logger.info(f"  Articles created: {results['total_articles']}")
        logger.info(f"  Ticker links: {results['total_ticker_links']}")

        print("✅ Incremental Reddit scraping completed successfully")

    except Exception as e:
        logger.error(f"Fatal error during incremental scraping: {e}")
        sys.exit(1)


def show_status(subreddit: str = "wallstreetbets") -> None:
    """Show current scraping status.

    Args:
        subreddit: Subreddit to check status for
    """
    setup_logging(False)

    try:
        # Get Reddit credentials
        client_id, client_secret, user_agent = get_reddit_credentials()
    except ValueError as e:
        print(f"❌ Reddit credentials not configured: {e}")
        return

    try:
        # Initialize scraper
        scraper = RedditIncrementalScraper()
        scraper.initialize_reddit(client_id, client_secret, user_agent)

        # Get status
        status = scraper.get_scraping_status(subreddit)

        if "error" in status:
            print(f"❌ Error getting status: {status['error']}")
            return

        print(f"📊 Reddit Scraping Status for r/{subreddit}")
        print(f"Total threads tracked: {status['total_threads']}")
        print(f"Total comments scraped: {status['total_comments_scraped']:,}")

        if status["recent_threads"]:
            print("\n📋 Recent Threads:")
            for i, thread in enumerate(status["recent_threads"][:5], 1):
                print(f"\n{i}. {thread['title']}")
                print(f"   Type: {thread['type']}")
                print(
                    f"   Comments: {thread['scraped_comments']:,}/{thread['total_comments']:,} ({thread['completion_rate']})"
                )
                print(f"   Last scraped: {thread['last_scraped'] or 'Never'}")
                print(f"   Complete: {'✅' if thread['is_complete'] else '⏳'}")

    except Exception as e:
        print(f"❌ Error getting status: {e}")


def main() -> None:
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Incremental Reddit discussion scraping CLI"
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Scrape command
    scrape_parser = subparsers.add_parser("scrape", help="Run incremental scraping")
    scrape_parser.add_argument(
        "--subreddit",
        type=str,
        default="wallstreetbets",
        help="Subreddit to scrape (default: wallstreetbets)",
    )
    scrape_parser.add_argument(
        "--max-threads",
        type=int,
        default=3,
        help="Maximum number of threads to process (default: 3)",
    )
    scrape_parser.add_argument(
        "--max-comments-per-thread",
        type=int,
        default=500,
        help="Maximum new comments per thread (default: 500)",
    )
    scrape_parser.add_argument(
        "--workers",
        type=int,
        default=5,
        help="Number of concurrent workers (default: 5)",
    )
    scrape_parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose logging",
    )

    # Status command
    status_parser = subparsers.add_parser("status", help="Show scraping status")
    status_parser.add_argument(
        "--subreddit",
        type=str,
        default="wallstreetbets",
        help="Subreddit to check status for (default: wallstreetbets)",
    )

    args = parser.parse_args()

    if args.command == "scrape":
        run_incremental_scrape(
            subreddit=args.subreddit,
            max_threads=args.max_threads,
            max_comments_per_thread=args.max_comments_per_thread,
            max_workers=args.workers,
            verbose=args.verbose,
        )
    elif args.command == "status":
        show_status(subreddit=args.subreddit)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
