#!/usr/bin/env python3
"""Send weekly digest emails job for ECS deployment."""

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


from app.config import settings  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.repos.user_repo import UserRepository  # noqa: E402
from app.repos.weekly_digest_repo import WeeklyDigestRepository  # noqa: E402
from app.services.email_service import get_email_service  # noqa: E402
from app.services.slack_service import SlackService  # noqa: E402
from app.services.weekly_digest_dispatch import (  # noqa: E402
    WeeklyDigestDispatchService,
    WeeklyDispatchStats,
)
from app.services.weekly_summary import (  # noqa: E402
    WeeklySummaryService,
    get_week_boundaries,
)

logger = logging.getLogger(__name__)

JOB_NAME = "send_weekly_digest"


def setup_logging(verbose: bool = False) -> None:
    """Setup structured logging."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )


def parse_week_dates(week_start: str | None, week_end: str | None) -> tuple[date, date]:
    """Parse week start/end dates or return previous week boundaries.

    Args:
        week_start: Start date string in YYYY-MM-DD format or None
        week_end: End date string in YYYY-MM-DD format or None

    Returns:
        Tuple of (week_start, week_end) dates
    """
    if week_start is None and week_end is None:
        boundaries = get_week_boundaries()
        logger.info(
            "Using previous week boundaries",
            extra={
                "week_start": boundaries.week_start.isoformat(),
                "week_end": boundaries.week_end.isoformat(),
            },
        )
        return boundaries.week_start, boundaries.week_end

    try:
        start = (
            datetime.strptime(week_start, "%Y-%m-%d").date()
            if week_start
            else get_week_boundaries().week_start
        )
        end = (
            datetime.strptime(week_end, "%Y-%m-%d").date()
            if week_end
            else start + timedelta(days=6)
        )
        return start, end
    except ValueError as exc:
        raise SystemExit(f"Invalid date value: {exc}") from exc


def format_stats(stats: WeeklyDispatchStats) -> str:
    """Format dispatch statistics for display.

    Args:
        stats: Weekly dispatch statistics

    Returns:
        Formatted string
    """
    lines = [
        "\n" + "=" * 60,
        "Weekly Digest Dispatch Results",
        "=" * 60,
        f"Week:               {stats.week_start} to {stats.week_end}",
        f"Total eligible:     {stats.total_eligible}",
        f"Emails sent:        {stats.sent}",
        f"Users skipped:      {stats.skipped}",
        f"Failed sends:       {stats.failed}",
    ]

    if stats.dry_run:
        lines.append("Mode:               DRY RUN (no emails sent)")

    lines.append("=" * 60)

    return "\n".join(lines)


def run_send_weekly_digest_job(
    week_start: date | None = None,
    week_end: date | None = None,
    dry_run: bool = False,
    verbose: bool = False,
    user_email: str | None = None,
    test_email_only: bool = False,
) -> dict[str, Any]:
    """Run the send weekly digest job.

    Args:
        week_start: Start of week (Monday). Defaults to previous week.
        week_end: End of week (Sunday). Defaults to previous week.
        dry_run: If True, log but don't send emails
        verbose: Enable verbose logging
        user_email: If provided, only send to this user (for testing)
        test_email_only: If True, only send to TEST_EMAIL_RECIPIENT

    Returns:
        Dictionary with job results and statistics
    """
    setup_logging(verbose)
    slack = SlackService()
    metadata: dict[str, Any] = {}
    start_time = datetime.now(UTC)
    thread_ts = slack.notify_job_start(JOB_NAME, metadata=metadata)

    # Resolve test email if --test-email-only
    if test_email_only:
        user_email = settings.test_email_recipient
        logger.info(
            "Test email mode: filtering to TEST_EMAIL_RECIPIENT only",
            extra={"test_email": user_email},
        )

    try:
        email_service = get_email_service()

        session = SessionLocal()
        try:
            user_repo = UserRepository(session)
            digest_repo = WeeklyDigestRepository(session)
            summary_service = WeeklySummaryService(session)

            # Determine week boundaries
            if week_start is None or week_end is None:
                boundaries = get_week_boundaries()
                week_start = week_start or boundaries.week_start
                week_end = week_end or boundaries.week_end

            logger.info(
                "Starting weekly digest job",
                extra={
                    "week_start": week_start.isoformat(),
                    "week_end": week_end.isoformat(),
                    "dry_run": dry_run,
                    "user_email": user_email,
                    "test_email_only": test_email_only,
                },
            )

            dispatch_service = WeeklyDigestDispatchService(
                session=session,
                email_service=email_service,
                user_repo=user_repo,
                digest_repo=digest_repo,
                summary_service=summary_service,
            )

            stats = dispatch_service.dispatch_weekly_digests(
                week_start=week_start,
                week_end=week_end,
                batch_size=settings.weekly_digest_batch_size,
                max_users=None,
                dry_run=dry_run,
                single_user_email=user_email,
                force=test_email_only,  # Bypass idempotency checks for test emails
            )

            # Commit the transaction
            session.commit()
            logger.info("Transaction committed successfully")

            print(format_stats(stats))

            duration = (datetime.now(UTC) - start_time).total_seconds()
            summary_metrics = {
                "week_start": stats.week_start.isoformat(),
                "week_end": stats.week_end.isoformat(),
                "total_eligible": stats.total_eligible,
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
        duration = (datetime.now(UTC) - start_time).total_seconds()
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
        description="Send weekly digest emails job",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Send weekly digests for the previous week
  python send_weekly_digest.py

  # Dry run to see what would be sent
  python send_weekly_digest.py --dry-run

  # Send to a specific user only (for testing)
  python send_weekly_digest.py --user-email test@example.com

  # Send for a specific week
  python send_weekly_digest.py --week-start 2025-12-01 --week-end 2025-12-07
        """,
    )

    parser.add_argument(
        "--week-start",
        help="YYYY-MM-DD start of week (Monday). Defaults to previous week.",
    )
    parser.add_argument(
        "--week-end",
        help="YYYY-MM-DD end of week (Sunday). Defaults to previous week.",
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
    parser.add_argument(
        "--user-email",
        help="Only send to this user email (for testing, not a dry-run)",
    )
    parser.add_argument(
        "--test-email-only",
        action="store_true",
        help="Only send to TEST_EMAIL_RECIPIENT (not a dry-run, actually sends)",
    )

    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Main entry point."""
    args = parse_args(argv)
    try:
        week_start, week_end = parse_week_dates(args.week_start, args.week_end)
        run_send_weekly_digest_job(
            week_start=week_start,
            week_end=week_end,
            dry_run=args.dry_run,
            verbose=args.verbose,
            user_email=args.user_email,
            test_email_only=args.test_email_only,
        )
        return 0
    except Exception as exc:  # noqa: BLE001
        logger.error("Send weekly digest job failed: %s", exc, exc_info=args.verbose)
        return 1


if __name__ == "__main__":
    sys.exit(main())
