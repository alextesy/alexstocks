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
from pathlib import Path
from typing import Any

# Load .env FIRST before any imports that might initialize settings
from dotenv import load_dotenv

# Load from project root (parent of jobs/ directory) since we run from jobs/
load_dotenv(dotenv_path=Path(__file__).parent.parent.parent / ".env")

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.append(str(ROOT_DIR))

from app.db.session import SessionLocal  # noqa: E402
from app.services.daily_summary import (  # noqa: E402
    DailySummaryResult,
    DailySummaryService,
)
from app.services.slack_service import SlackService  # noqa: E402
from jobs.slack_wrapper import run_with_slack  # noqa: E402

from .reddit_discussion_scraper import get_reddit_credentials  # noqa: E402
from .reddit_scraper import RedditScraper  # noqa: E402

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
    config_path: str | None = None,
    subreddit: str | None = None,
    max_threads: int = 3,
    max_replace_more: int | None = 32,
    verbose: bool = False,
) -> dict[str, Any]:
    """
    Run incremental scraping (for 15-min cron jobs).

    Args:
        config_path: Path to config file (if None, uses default)
        subreddit: Specific subreddit to scrape (if None, scrapes all enabled in config)
        max_threads: DEPRECATED - kept for backwards compat
        max_replace_more: DEPRECATED - kept for backwards compat
        verbose: Enable verbose logging
    """
    setup_logging(verbose)

    if subreddit:
        logger.info(f"🚀 Starting INCREMENTAL scraping for r/{subreddit}")
    else:
        logger.info("🚀 Starting INCREMENTAL scraping (all enabled subreddits)")

    try:
        # Get credentials
        client_id, client_secret, user_agent = get_reddit_credentials()
    except ValueError as e:
        logger.error(f"❌ Missing credentials: {e}")
        sys.exit(1)

    try:
        # Initialize scraper with config
        scraper = RedditScraper(config_path=config_path)
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

        # Return stats for Slack summary
        return {
            "threads_processed": stats.threads_processed,
            "total_comments": stats.total_comments,
            "new_comments": stats.new_comments,
            "articles_created": stats.articles_created,
            "ticker_links": stats.ticker_links,
            "batches_saved": stats.batches_saved,
            "success": stats.new_comments,
            "duration": stats.duration_ms / 1000.0,
        }

    except Exception as e:
        logger.error(f"❌ Fatal error: {e}", exc_info=True)
        raise


def run_backfill(
    subreddit: str,
    start_date: str,
    end_date: str,
    config_path: str | None = None,
    max_replace_more: int | None = 32,
    verbose: bool = False,
) -> dict[str, Any]:
    """
    Run backfill for date range.

    Args:
        subreddit: Subreddit to scrape
        start_date: Start date (YYYY-MM-DD)
        end_date: End date (YYYY-MM-DD)
        config_path: Path to config file (if None, uses default)
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
        # Initialize scraper with config
        scraper = RedditScraper(config_path=config_path)
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

        # Return stats for Slack summary
        return {
            "threads_processed": stats.threads_processed,
            "total_comments": stats.total_comments,
            "new_comments": stats.new_comments,
            "articles_created": stats.articles_created,
            "ticker_links": stats.ticker_links,
            "batches_saved": stats.batches_saved,
            "success": stats.new_comments,
            "duration": stats.duration_ms / 1000.0,
        }

    except Exception as e:
        logger.error(f"❌ Fatal error: {e}", exc_info=True)
        raise


def show_status(
    config_path: str | None = None,
    subreddit: str = "wallstreetbets",
    verbose: bool = False,
) -> dict[str, Any]:
    """Collect and display scraping status."""

    try:
        status = collect_status(
            config_path=config_path, subreddit=subreddit, verbose=verbose
        )
    except Exception as exc:  # noqa: BLE001
        print(f"❌ Error: {exc}")
        if verbose:
            logger.error("Error details:", exc_info=True)
        return {}

    _print_status(status, subreddit)
    return status


def collect_status(
    config_path: str | None = None,
    subreddit: str = "wallstreetbets",
    verbose: bool = False,
) -> dict[str, Any]:
    """Collect scraping status from Reddit."""

    setup_logging(verbose)

    # Get credentials
    client_id, client_secret, user_agent = get_reddit_credentials()

    scraper = RedditScraper(config_path=config_path)
    scraper.initialize_reddit(client_id, client_secret, user_agent)

    status = scraper.get_scraping_status(subreddit, check_live_counts=True)
    if "error" in status:
        raise RuntimeError(status["error"])
    return status


def _print_status(status: dict[str, Any], subreddit: str) -> None:
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
            print(f"   Complete:     {'✅ Yes' if thread['is_complete'] else '⏳ No'}")

    print(f"\n{'=' * 60}\n")


def _summarize_daily_mentions() -> tuple[DailySummaryResult | None, list[str]]:
    session = SessionLocal()
    try:
        service = DailySummaryService(session)
        summary = service.load_previous_day_summary()
        if not summary.tickers:
            return summary, []

        try:
            responses = service.generate_langchain_summary(summary)
        except (RuntimeError, ValueError) as exc:
            logger.warning("LangChain invocation skipped: %s", exc)
            responses = []
        return summary, responses
    finally:
        session.close()


def _format_summary_for_slack(
    subreddit: str,
    status: dict[str, Any],
    summary: DailySummaryResult | None,
    responses: list[str],
) -> str:
    lines = [
        f"Daily status for r/{subreddit}",
        f"Threads tracked: {status['total_threads']}",
        f"Total comments scraped: {status['total_comments_scraped']:,}",
    ]

    if summary:
        lines.append(
            f"Daily summary tickers: {len(summary.tickers)} (mentions {summary.total_mentions})"
        )
        if summary.tickers:
            top = ", ".join(ticker.ticker for ticker in summary.tickers)
            lines.append(f"Top tickers: {top}")
    else:
        lines.append("Daily summary unavailable")

    if responses:
        lines.append("\nLLM summary:")
        lines.extend(responses)
    elif summary and not summary.tickers:
        lines.append("No tickers met the summary thresholds yesterday.")

    return "\n".join(lines)


def run_status_job(
    config_path: str | None = None,
    subreddit: str = "wallstreetbets",
    verbose: bool = False,
) -> dict[str, Any]:
    """Run the daily status check with Slack and LLM summaries."""

    setup_logging(verbose)
    slack = SlackService()
    metadata = {"subreddit": subreddit}
    start = datetime.now(UTC)
    thread_ts = slack.notify_job_start("daily_status", metadata=metadata)

    try:
        status = collect_status(
            config_path=config_path, subreddit=subreddit, verbose=verbose
        )
        _print_status(status, subreddit)

        summary, responses = _summarize_daily_mentions()
        if summary:
            print("Daily summary tickers:")
            for ticker in summary.tickers:
                print(f" - {ticker.ticker}: {ticker.mentions} mentions")
        if responses:
            print("\nLangChain responses:")
            for response in responses:
                print(response)

        slack_text = _format_summary_for_slack(subreddit, status, summary, responses)
        slack.send_message(text=slack_text, thread_ts=thread_ts)

        duration = (datetime.now(UTC) - start).total_seconds()
        summary_metrics = {
            "threads": status.get("total_threads"),
            "tickers": len(summary.tickers) if summary else 0,
            "mentions": summary.total_mentions if summary else 0,
        }
        slack.notify_job_complete(
            job_name="daily_status",
            status="success",
            duration_seconds=duration,
            summary=summary_metrics,
            thread_ts=thread_ts,
        )
        return {
            "status": status,
            "summary": summary_metrics,
            "responses": responses,
        }
    except Exception as exc:
        duration = (datetime.now(UTC) - start).total_seconds()
        slack.notify_job_complete(
            job_name="daily_status",
            status="error",
            duration_seconds=duration,
            summary={"subreddit": subreddit},
            error=str(exc),
            thread_ts=thread_ts,
        )
        raise


def main() -> None:
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Production Reddit Scraper CLI - Multi-subreddit support with YAML config",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Incremental scraping (all enabled subreddits from config)
  python -m ingest.reddit_scraper_cli --mode incremental

  # Incremental with custom config
  python -m ingest.reddit_scraper_cli --mode incremental --config my_config.yaml

  # Incremental for specific subreddit (overrides config)
  python -m ingest.reddit_scraper_cli --mode incremental --subreddit wallstreetbets

  # Backfill historical data
  python -m ingest.reddit_scraper_cli --mode backfill --subreddit wallstreetbets --start 2025-09-01 --end 2025-09-30

  # Check status
  python -m ingest.reddit_scraper_cli --mode status

  # Verbose mode
  python -m ingest.reddit_scraper_cli --mode incremental --verbose
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
        "--config",
        type=str,
        help="Path to YAML config file (default: config/reddit_scraper_config.yaml)",
    )

    parser.add_argument(
        "--subreddit",
        type=str,
        help="Specific subreddit to scrape (if not set, uses enabled subreddits from config)",
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

        def run_job():
            return run_incremental(
                config_path=args.config,
                subreddit=args.subreddit,
                max_threads=args.max_threads,
                max_replace_more=max_replace_more,
                verbose=args.verbose,
            )

        run_with_slack(
            job_name="reddit_scraper",
            job_func=run_job,
            metadata={
                "mode": "incremental",
                "subreddit": args.subreddit or "all",
            },
        )
    elif args.mode == "backfill":
        if not args.subreddit:
            parser.error("--mode backfill requires --subreddit")

        def run_job():
            return run_backfill(
                subreddit=args.subreddit,
                start_date=args.start,
                end_date=args.end,
                config_path=args.config,
                max_replace_more=max_replace_more,
                verbose=args.verbose,
            )

        run_with_slack(
            job_name="reddit_scraper_backfill",
            job_func=run_job,
            metadata={
                "mode": "backfill",
                "subreddit": args.subreddit,
                "start_date": args.start,
                "end_date": args.end,
            },
        )
    elif args.mode == "status":
        try:
            run_status_job(
                config_path=args.config,
                subreddit=args.subreddit or "wallstreetbets",
                verbose=args.verbose,
            )
        except Exception as exc:  # noqa: BLE001
            logger.error("Daily status job failed: %s", exc, exc_info=args.verbose)
            sys.exit(1)


if __name__ == "__main__":
    main()
