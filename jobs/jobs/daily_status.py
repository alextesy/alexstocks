"""Daily status job that checks Reddit scraping status and generates daily summaries."""

from __future__ import annotations

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
from jobs.ingest.reddit_discussion_scraper import get_reddit_credentials  # noqa: E402
from jobs.ingest.reddit_scraper import RedditScraper  # noqa: E402

logger = logging.getLogger(__name__)

JOB_NAME = "daily_status"


def setup_logging(verbose: bool = False) -> None:
    """Setup structured logging."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )


def collect_reddit_status(
    config_path: str | None = None,
    subreddit: str | None = None,
    verbose: bool = False,
) -> dict[str, Any]:
    """Collect scraping status from Reddit for a single subreddit or all enabled subreddits.

    Args:
        config_path: Path to YAML config file
        subreddit: Specific subreddit name (if None, aggregates status for all enabled subreddits)
        verbose: Enable verbose logging

    Returns:
        Dictionary with scraping status
    """

    setup_logging(verbose)

    # Get credentials
    client_id, client_secret, user_agent = get_reddit_credentials()

    scraper = RedditScraper(config_path=config_path)
    scraper.initialize_reddit(client_id, client_secret, user_agent)

    # If subreddit is specified, get status for that one
    if subreddit:
        status = scraper.get_scraping_status(subreddit, check_live_counts=True)
        if "error" in status:
            raise RuntimeError(status["error"])
        return status

    # Otherwise, aggregate status for all enabled subreddits
    config = scraper.config
    enabled_subreddits = config.get_enabled_subreddits()

    if not enabled_subreddits:
        raise RuntimeError("No enabled subreddits found in config")

    # Aggregate status across all subreddits
    overall_status: dict[str, Any] = {
        "total_threads": 0,
        "total_comments_scraped": 0,
        "live_counts_enabled": True,
        "recent_threads": [],
        "subreddits": {},
    }

    for sub_config in enabled_subreddits:
        subreddit_name = sub_config.name
        try:
            sub_status = scraper.get_scraping_status(
                subreddit_name, check_live_counts=True
            )
            if "error" in sub_status:
                logger.warning(
                    f"Error getting status for r/{subreddit_name}: {sub_status['error']}"
                )
                continue

            # Aggregate totals
            overall_status["total_threads"] += sub_status.get("total_threads", 0)
            overall_status["total_comments_scraped"] += sub_status.get(
                "total_comments_scraped", 0
            )

            # Store per-subreddit status
            overall_status["subreddits"][subreddit_name] = {
                "total_threads": sub_status.get("total_threads", 0),
                "total_comments_scraped": sub_status.get("total_comments_scraped", 0),
                "recent_threads": sub_status.get("recent_threads", [])[:3],
            }

            # Collect recent threads (up to 5 per subreddit, max 20 total)
            if len(overall_status["recent_threads"]) < 20:
                recent = sub_status.get("recent_threads", [])[:5]
                for thread in recent:
                    thread["subreddit"] = subreddit_name
                    overall_status["recent_threads"].append(thread)

        except Exception as e:
            logger.warning(
                f"Error collecting status for r/{subreddit_name}: {e}", exc_info=verbose
            )
            continue

    # Sort recent threads by last_scraped (most recent first)
    # Use last_scraped as a proxy for recency
    overall_status["recent_threads"].sort(
        key=lambda x: x.get("last_scraped") or "", reverse=True
    )
    overall_status["recent_threads"] = overall_status["recent_threads"][:20]

    return overall_status


def _print_status(status: dict[str, Any], subreddit: str | None = None) -> None:
    """Print status information to console."""
    is_overall = subreddit is None

    print(f"\n{'=' * 60}")
    if is_overall:
        print("📊 REDDIT SCRAPING STATUS - ALL SUBREDDITS")
    else:
        print(f"📊 REDDIT SCRAPING STATUS - r/{subreddit}")
    print(f"{'=' * 60}")
    print(f"Total threads tracked:   {status['total_threads']}")
    print(f"Total comments scraped:  {status['total_comments_scraped']:,}")
    print(f"Live counts enabled:     {status.get('live_counts_enabled', True)}")

    # Show per-subreddit breakdown if overall status
    if is_overall and "subreddits" in status:
        print(f"\n{'─' * 60}")
        print("📊 PER-SUBREDDIT BREAKDOWN")
        print(f"{'─' * 60}")
        for sub_name, sub_data in sorted(status["subreddits"].items()):
            print(
                f"r/{sub_name}: {sub_data['total_threads']} threads, "
                f"{sub_data['total_comments_scraped']:,} comments"
            )

    if status.get("recent_threads"):
        print(f"\n{'─' * 60}")
        print("📋 RECENT THREADS")
        print(f"{'─' * 60}")

        for i, thread in enumerate(status["recent_threads"][:10], 1):
            thread_subreddit = thread.get("subreddit", "")
            subreddit_label = f"r/{thread_subreddit} - " if thread_subreddit else ""
            print(f"\n{i}. {subreddit_label}{thread['title']}")
            print(f"   Type:        {thread['type']}")
            print(
                f"   Progress:    {thread['scraped_comments']:,} / {thread['total_comments']:,} "
                f"({thread['completion_rate']})"
            )
            print(f"   Last scraped: {thread['last_scraped'] or 'Never'}")
            print(f"   Complete:     {'✅ Yes' if thread['is_complete'] else '⏳ No'}")

    print(f"\n{'=' * 60}\n")


def generate_daily_summary(
    max_tickers: int | None = None,
) -> tuple[DailySummaryResult | None, list[str]]:
    """Generate daily summary with LLM responses.

    Args:
        max_tickers: Maximum number of tickers to include. If None, uses default from settings.
    """
    session = SessionLocal()
    try:
        service = DailySummaryService(session)
        summary = service.load_previous_day_summary(max_tickers=max_tickers)
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


def format_summary_for_slack(
    subreddit: str | None,
    status: dict[str, Any],
    summary: DailySummaryResult | None,
    responses: list[str],
) -> str:
    """Format the complete status and summary for Slack."""
    if subreddit:
        lines = [
            f"Daily status for r/{subreddit}",
            f"Threads tracked: {status['total_threads']}",
            f"Total comments scraped: {status['total_comments_scraped']:,}",
        ]
    else:
        lines = [
            "Daily status for all subreddits",
            f"Total threads tracked: {status['total_threads']}",
            f"Total comments scraped: {status['total_comments_scraped']:,}",
        ]
        # Add per-subreddit breakdown
        if "subreddits" in status:
            lines.append("\nPer-subreddit:")
            for sub_name, sub_data in sorted(status["subreddits"].items()):
                lines.append(
                    f"  r/{sub_name}: {sub_data['total_threads']} threads, "
                    f"{sub_data['total_comments_scraped']:,} comments"
                )

    if summary:
        lines.append(
            f"Daily summary tickers: {len(summary.tickers)} (mentions {summary.total_mentions})"
        )
        if summary.tickers:
            top = ", ".join(ticker_summary.ticker for ticker_summary in summary.tickers)
            lines.append(f"Top tickers: {top}")
    else:
        lines.append("Daily summary unavailable")

    if responses:
        lines.append("\nLLM summary:")
        # Format responses with ticker labels
        for idx, response in enumerate(responses):
            if summary and idx < len(summary.tickers):
                ticker_symbol = summary.tickers[idx].ticker
                lines.append(f"\n**{ticker_symbol}:**")
            lines.append(response)
    elif summary and not summary.tickers:
        lines.append("No tickers met the summary thresholds yesterday.")

    return "\n".join(lines)


def run_daily_status_job(
    config_path: str | None = None,
    subreddit: str | None = None,
    verbose: bool = False,
) -> dict[str, Any]:
    """Run the daily status check with Slack and LLM summaries.

    Args:
        config_path: Path to YAML config file
        subreddit: Specific subreddit (if None, aggregates all enabled subreddits)
        verbose: Enable verbose logging
    """

    setup_logging(verbose)
    slack = SlackService()
    metadata = {"subreddit": subreddit or "all"}
    start = datetime.now(UTC)
    thread_ts = slack.notify_job_start(JOB_NAME, metadata=metadata)

    try:
        # Collect Reddit scraping status
        status = collect_reddit_status(
            config_path=config_path, subreddit=subreddit, verbose=verbose
        )
        _print_status(status, subreddit)

        # Generate daily summary (limit to 3 tickers for testing)
        summary, responses = generate_daily_summary(max_tickers=3)
        if summary:
            print("Daily summary tickers:")
            for ticker_summary in summary.tickers:
                print(f" - {ticker_summary.ticker}: {ticker_summary.mentions} mentions")
        if responses:
            print("\nLangChain responses:")
            for idx, response in enumerate(responses):
                if summary and idx < len(summary.tickers):
                    ticker_symbol = summary.tickers[idx].ticker
                    print(f"\n[{ticker_symbol}]")
                print(response)

        # Send formatted message to Slack
        slack_text = format_summary_for_slack(subreddit, status, summary, responses)
        slack.send_message(text=slack_text, thread_ts=thread_ts)

        duration = (datetime.now(UTC) - start).total_seconds()
        summary_metrics = {
            "threads": status.get("total_threads"),
            "tickers": len(summary.tickers) if summary else 0,
            "mentions": summary.total_mentions if summary else 0,
            "responses": len(responses),
            "subreddit": subreddit or "all",
        }
        slack.notify_job_complete(
            job_name=JOB_NAME,
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
            job_name=JOB_NAME,
            status="error",
            duration_seconds=duration,
            summary={"subreddit": subreddit or "all"},
            error=str(exc),
            thread_ts=thread_ts,
        )
        raise


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Daily status job - Reddit scraping status and daily summaries",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "--config",
        type=str,
        help="Path to YAML config file (default: config/reddit_scraper_config.yaml)",
    )

    parser.add_argument(
        "--subreddit",
        type=str,
        default=None,
        help="Specific subreddit to check (if not set, aggregates all enabled subreddits)",
    )

    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose logging",
    )

    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Main entry point."""
    args = parse_args(argv)
    try:
        run_daily_status_job(
            config_path=args.config,
            subreddit=args.subreddit,
            verbose=args.verbose,
        )
        return 0
    except Exception as exc:  # noqa: BLE001
        logger.error("Daily status job failed: %s", exc, exc_info=args.verbose)
        return 1


if __name__ == "__main__":
    sys.exit(main())
