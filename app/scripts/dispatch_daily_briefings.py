#!/usr/bin/env python3
"""Dispatch daily briefing emails to all eligible users."""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import date, datetime, timedelta

from app.db.session import SessionLocal
from app.repos.email_send_log_repo import EmailSendLogRepository
from app.repos.summary_repo import DailyTickerSummaryRepository
from app.repos.user_repo import UserRepository
from app.services.email_dispatch_service import DispatchStats, EmailDispatchService
from app.services.email_service import get_email_service

logger = logging.getLogger(__name__)


def setup_logging(verbose: bool = False) -> None:
    """Configure logging for the script."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
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
        raise SystemExit(f"Invalid --summary-date value: {value}") from exc


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


def main() -> int:
    """Main entry point for the dispatch script."""
    parser = argparse.ArgumentParser(
        description="Dispatch daily briefing emails to all eligible users"
    )
    parser.add_argument(
        "--summary-date",
        help="YYYY-MM-DD date to use for summaries (defaults to previous day)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Dry run mode - log what would be sent but don't actually send",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=50,
        help="Number of users to process per batch (default: 50)",
    )
    parser.add_argument(
        "--max-users",
        type=int,
        default=None,
        help="Maximum number of users to process (default: no limit)",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose logging",
    )

    args = parser.parse_args()

    setup_logging(verbose=args.verbose)

    summary_date = parse_summary_date(args.summary_date)
    email_service = get_email_service()

    with SessionLocal() as session:
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

        try:
            stats = dispatch_service.dispatch_daily_briefings(
                summary_date=summary_date,
                batch_size=args.batch_size,
                max_users=args.max_users,
                dry_run=args.dry_run,
            )

            # Commit the transaction to persist EmailSendLog entries
            session.commit()
            logger.info("Transaction committed successfully")

            print(format_stats(stats))

            # Exit with error code if there were failures
            if stats.failed > 0:
                return 1

            return 0

        except KeyboardInterrupt:
            print("\n\n⚠️  Dispatch interrupted by user")
            session.rollback()
            logger.warning("Transaction rolled back due to user interrupt")
            return 130
        except Exception as e:
            print(f"\n❌ Error during dispatch: {e}", file=sys.stderr)
            logging.exception("Dispatch failed")
            session.rollback()
            logger.error("Transaction rolled back due to error")
            return 1


if __name__ == "__main__":
    sys.exit(main())
