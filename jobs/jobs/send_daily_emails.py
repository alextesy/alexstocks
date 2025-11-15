#!/usr/bin/env python3
"""Send daily briefing emails job for ECS deployment."""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import UTC, date, datetime, timedelta
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
from app.repos.email_send_log_repo import EmailSendLogRepository  # noqa: E402
from app.repos.summary_repo import DailyTickerSummaryRepository  # noqa: E402
from app.repos.user_repo import UserRepository  # noqa: E402
from app.services.email_dispatch_service import (  # noqa: E402
    DispatchStats,
    EmailDispatchService,
)
from app.services.email_service import get_email_service  # noqa: E402
from app.services.slack_service import SlackService  # noqa: E402

logger = logging.getLogger(__name__)

JOB_NAME = "send_daily_emails"


def setup_logging(verbose: bool = False) -> None:
    """Setup structured logging."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )


def parse_summary_date(value: str | None) -> date:
    """Parse summary date from string or return previous day.

    Args:
        value: Date string in YYYY-MM-DD format or None

    Returns:
        Parsed date or previous day if None
    """
    if not value:
        return date.today() - timedelta(days=1)

    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as exc:
        raise SystemExit(f"Invalid --date value: {value}") from exc


def format_stats(stats: DispatchStats) -> str:
    """Format dispatch statistics for display.

    Args:
        stats: Dispatch statistics

    Returns:
        Formatted string
    """
    lines = [
        "\n" + "=" * 60,
        "Daily Briefing Dispatch Results",
        "=" * 60,
        f"Total eligible users: {stats.total_users}",
        f"Emails sent:        {stats.sent}",
        f"Users skipped:      {stats.skipped}",
        f"Failed sends:       {stats.failed}",
    ]

    if stats.dry_run:
        lines.append("Mode:              DRY RUN (no emails sent)")

    lines.append("=" * 60)

    return "\n".join(lines)


def run_send_daily_emails_job(
    summary_date: date | None = None,
    dry_run: bool = False,
    verbose: bool = False,
) -> dict[str, Any]:
    """Run the send daily emails job.

    Args:
        summary_date: Target summary date (defaults to previous UTC day)
        dry_run: If True, log but don't send emails
        verbose: Enable verbose logging

    Returns:
        Dictionary with job results and statistics
    """
    setup_logging(verbose)
    slack = SlackService()
    metadata: dict[str, Any] = {}
    start = datetime.now(UTC)
    thread_ts = slack.notify_job_start(JOB_NAME, metadata=metadata)

    try:
        # Determine summary date
        if summary_date is None:
            summary_date = date.today() - timedelta(days=1)

        logger.info(
            "Starting daily email dispatch job",
            extra={
                "summary_date": summary_date.isoformat(),
                "dry_run": dry_run,
            },
        )

        email_service = get_email_service()

        session = SessionLocal()
        try:
            user_repo = UserRepository(session)
            summary_repo = DailyTickerSummaryRepository(session)
            send_log_repo = EmailSendLogRepository(session)

            dispatch_service = EmailDispatchService(
                session=session,
                email_service=email_service,
                user_repo=user_repo,
                summary_repo=summary_repo,
                send_log_repo=send_log_repo,
            )

            stats = dispatch_service.dispatch_daily_briefings(
                summary_date=summary_date,
                batch_size=50,
                max_users=None,
                dry_run=dry_run,
            )

            # Commit the transaction to persist EmailSendLog entries
            session.commit()
            logger.info("Transaction committed successfully")

            print(format_stats(stats))

            duration = (datetime.now(UTC) - start).total_seconds()
            summary_metrics = {
                "total_users": stats.total_users,
                "sent": stats.sent,
                "skipped": stats.skipped,
                "failed": stats.failed,
                "dry_run": stats.dry_run,
            }
            slack.notify_job_complete(
                job_name=JOB_NAME,
                status="success" if stats.failed == 0 else "partial",
                duration_seconds=duration,
                summary=summary_metrics,
                thread_ts=thread_ts,
            )

            return {
                "stats": summary_metrics,
                "duration_seconds": duration,
            }
        finally:
            session.close()

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
        description="Send daily briefing emails job",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "--date",
        help="YYYY-MM-DD date to use for summaries (defaults to previous day)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Dry run mode - log what would be sent but don't actually send",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose logging",
    )

    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Main entry point."""
    args = parse_args(argv)
    try:
        summary_date = parse_summary_date(args.date)
        run_send_daily_emails_job(
            summary_date=summary_date,
            dry_run=args.dry_run,
            verbose=args.verbose,
        )
        return 0
    except Exception as exc:  # noqa: BLE001
        logger.error("Send daily emails job failed: %s", exc, exc_info=args.verbose)
        return 1


if __name__ == "__main__":
    sys.exit(main())
