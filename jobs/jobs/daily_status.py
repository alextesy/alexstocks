"""Daily status job that generates daily summaries."""

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
    summary: DailySummaryResult | None,
    responses: list[str],
) -> str:
    """Format the daily summary for Slack."""
    lines = ["Daily Summary"]

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
    verbose: bool = False,
) -> dict[str, Any]:
    """Run the daily status check with Slack and LLM summaries.

    Args:
        verbose: Enable verbose logging
    """

    setup_logging(verbose)
    slack = SlackService()
    metadata: dict[str, Any] = {}
    start = datetime.now(UTC)
    thread_ts = slack.notify_job_start(JOB_NAME, metadata=metadata)

    try:
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
        slack_text = format_summary_for_slack(summary, responses)
        slack.send_message(text=slack_text, thread_ts=thread_ts)

        duration = (datetime.now(UTC) - start).total_seconds()
        summary_metrics = {
            "tickers": len(summary.tickers) if summary else 0,
            "mentions": summary.total_mentions if summary else 0,
            "responses": len(responses),
        }
        slack.notify_job_complete(
            job_name=JOB_NAME,
            status="success",
            duration_seconds=duration,
            summary=summary_metrics,
            thread_ts=thread_ts,
        )
        return {
            "summary": summary_metrics,
            "responses": responses,
        }
    except Exception as exc:
        duration = (datetime.now(UTC) - start).total_seconds()
        slack.notify_job_complete(
            job_name=JOB_NAME,
            status="error",
            duration_seconds=duration,
            summary={},
            error=str(exc),
            thread_ts=thread_ts,
        )
        raise


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Daily status job - Daily summaries",
        formatter_class=argparse.RawDescriptionHelpFormatter,
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
        run_daily_status_job(verbose=args.verbose)
        return 0
    except Exception as exc:  # noqa: BLE001
        logger.error("Daily status job failed: %s", exc, exc_info=args.verbose)
        return 1


if __name__ == "__main__":
    sys.exit(main())
