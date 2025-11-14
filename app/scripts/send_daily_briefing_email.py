#!/usr/bin/env python3
"""Send a sample daily briefing email to the configured test recipient."""

from __future__ import annotations

import argparse
import sys
from datetime import date, datetime, timedelta

from app.config import settings
from app.db.session import SessionLocal
from app.models.dto import DailyTickerSummaryDTO
from app.repos.summary_repo import DailyTickerSummaryRepository
from app.repos.user_repo import UserRepository
from app.services.email_service import get_email_service


def parse_summary_date(value: str | None) -> date:
    """Return requested summary date or default to previous day."""
    if not value:
        return date.today() - timedelta(days=1)

    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as exc:  # pragma: no cover - handled by CLI validation
        raise SystemExit(f"Invalid --summary-date value: {value}") from exc


def collect_summaries(
    repo: DailyTickerSummaryRepository, tickers: list[str], summary_date: date
) -> list[DailyTickerSummaryDTO]:
    """Fetch summaries for target date with fallback to most recent records."""
    if not tickers:
        return []

    summaries = repo.get_summaries(
        tickers=tickers, start_date=summary_date, end_date=summary_date
    )
    if summaries:
        return summaries

    fallback_limit = max(len(tickers) * 2, settings.email_daily_briefing_max_tickers)
    fallback = repo.get_summaries(tickers=tickers, limit=fallback_limit)

    deduped: dict[str, DailyTickerSummaryDTO] = {}
    for summary in fallback:
        key = summary.ticker.upper()
        if key not in deduped:
            deduped[key] = summary
    return list(deduped.values())


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Send a personalized daily briefing email to TEST_EMAIL_RECIPIENT "
            "using the latest ticker summaries."
        )
    )
    parser.add_argument(
        "--summary-date",
        help="YYYY-MM-DD date to use for summaries (defaults to previous day)",
    )
    args = parser.parse_args()

    target_email = settings.test_email_recipient
    if not target_email:
        print("❌ TEST_EMAIL_RECIPIENT is not configured in the environment.")
        return 1

    summary_date = parse_summary_date(args.summary_date)
    email_service = get_email_service()

    with SessionLocal() as session:
        user_repo = UserRepository(session)
        summary_repo = DailyTickerSummaryRepository(session)

        user = user_repo.get_user_by_email(target_email)
        if not user:
            print(
                f"❌ No user found with email {target_email}. "
                "Create the user or update TEST_EMAIL_RECIPIENT."
            )
            return 1

        profile = user_repo.get_profile(user.id)
        follows = user_repo.get_ticker_follows(user.id)

        if not follows:
            print(f"❌ User {target_email} has no watchlist tickers configured.")
            return 1

        tickers = [follow.ticker for follow in follows]
        summaries = collect_summaries(summary_repo, tickers, summary_date)

        if not summaries:
            print(
                f"❌ No ticker summaries available for {summary_date.isoformat()} "
                f"or any recent date for watchlist tickers: {', '.join(tickers)}."
            )
            return 1

        unsubscribe_token = f"preview-{user.id}"
        print(
            f"📧 Sending daily briefing to {target_email} "
            f"for {len(summaries)} tickers (target date {summary_date.isoformat()})..."
        )

        result = email_service.send_summary_email(
            user,
            summaries,
            user_profile=profile,
            user_ticker_follows=follows,
            unsubscribe_token=unsubscribe_token,
        )

        if result.success:
            print("✅ Daily briefing sent successfully!")
            if result.message_id:
                print(f"   Message ID: {result.message_id}")
            return 0

        print("❌ Failed to send daily briefing email.")
        if result.error:
            print(f"   Error: {result.error}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
