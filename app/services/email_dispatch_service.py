"""Email dispatch service for batch sending daily briefing emails."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy.orm import Session

from app.models.dto import (
    DailyTickerSummaryDTO,
    EmailSendResult,
    UserDTO,
)
from app.repos.email_send_log_repo import EmailSendLogRepository
from app.repos.summary_repo import DailyTickerSummaryRepository
from app.repos.user_repo import UserRepository
from app.services.email_service import EmailService
from app.services.email_utils import generate_unsubscribe_token

logger = logging.getLogger(__name__)


@dataclass
class DispatchStats:
    """Statistics from a dispatch run."""

    total_users: int
    sent: int
    skipped: int
    failed: int
    dry_run: bool


class EmailDispatchService:
    """Service for dispatching daily briefing emails to users."""

    def __init__(
        self,
        session: Session,
        email_service: EmailService,
        user_repo: UserRepository | None = None,
        summary_repo: DailyTickerSummaryRepository | None = None,
        send_log_repo: EmailSendLogRepository | None = None,
    ):
        """Initialize dispatch service.

        Args:
            session: Database session
            email_service: Email service for sending emails
            user_repo: User repository (created if not provided)
            summary_repo: Summary repository (created if not provided)
            send_log_repo: Send log repository (created if not provided)
        """
        self.session = session
        self.email_service = email_service
        self.user_repo = user_repo or UserRepository(session)
        self.summary_repo = summary_repo or DailyTickerSummaryRepository(session)
        self.send_log_repo = send_log_repo or EmailSendLogRepository(session)

    def get_eligible_users(self) -> list[UserDTO]:
        """Get all users eligible for daily briefing emails.

        Returns:
            List of users with daily briefing enabled
        """
        return self.user_repo.get_users_with_daily_briefing_enabled()

    def filter_users_with_summaries(
        self, users: list[UserDTO], summary_date: date
    ) -> list[tuple[UserDTO, list[DailyTickerSummaryDTO]]]:
        """Filter users who have summaries for their followed tickers.

        Args:
            users: List of eligible users
            summary_date: Target summary date

        Returns:
            List of tuples (user, summaries) for users with summaries
        """
        result: list[tuple[UserDTO, list[DailyTickerSummaryDTO]]] = []

        for user in users:
            follows = self.user_repo.get_ticker_follows(user.id)
            if not follows:
                logger.debug(
                    "Skipping user - no ticker follows",
                    extra={"user_id": user.id, "user_email": user.email},
                )
                continue

            tickers = [follow.ticker for follow in follows]
            summaries = self.summary_repo.get_summaries(
                tickers=tickers, start_date=summary_date, end_date=summary_date
            )

            # Filter to only summaries with llm_summary (not null)
            summaries_with_content = [s for s in summaries if s.llm_summary is not None]

            if not summaries_with_content:
                logger.debug(
                    "Skipping user - no summaries with content",
                    extra={
                        "user_id": user.id,
                        "user_email": user.email,
                        "tickers": tickers,
                    },
                )
                continue

            result.append((user, summaries_with_content))

        return result

    def send_batch(
        self,
        batch: list[tuple[UserDTO, list[DailyTickerSummaryDTO]]],
        summary_date: date,
        dry_run: bool = False,
    ) -> tuple[int, int]:
        """Send emails to a batch of users.

        Args:
            batch: List of (user, summaries) tuples
            summary_date: Summary date
            dry_run: If True, log but don't send

        Returns:
            Tuple of (sent_count, failed_count)
        """
        sent = 0
        failed = 0
        rate_limit_delay = 1.0 / 14.0  # 14 emails per second

        for idx, (user, summaries) in enumerate(batch):
            try:
                profile = self.user_repo.get_profile(user.id)
                follows = self.user_repo.get_ticker_follows(user.id)

                unsubscribe_token = generate_unsubscribe_token(user.id)

                if dry_run:
                    logger.info(
                        "DRY RUN: Would send email",
                        extra={
                            "user_id": user.id,
                            "user_email": user.email,
                            "ticker_count": len(summaries),
                            "summary_date": summary_date.isoformat(),
                        },
                    )
                    # Create a mock success result for dry run
                    result = EmailSendResult(
                        success=True,
                        message_id="dry-run-message-id",
                        error=None,
                        provider=self.email_service.provider_name,
                    )
                    sent += 1
                else:
                    result = self.email_service.send_summary_email(
                        user=user,
                        ticker_summaries=summaries,
                        user_profile=profile,
                        user_ticker_follows=follows,
                        unsubscribe_token=unsubscribe_token,
                    )

                    if result.success:
                        sent += 1
                    else:
                        failed += 1

                    # Rate limiting: sleep between sends (except after last one)
                    if idx < len(batch) - 1:
                        time.sleep(rate_limit_delay)

                # Log the send attempt
                self.send_log_repo.create_log_entry(
                    user_id=user.id,
                    email_address=user.email,
                    summary_date=summary_date,
                    ticker_count=len(summaries),
                    result=result,
                )

            except Exception as e:
                logger.error(
                    "Error sending email to user",
                    extra={
                        "user_id": user.id,
                        "user_email": user.email,
                        "error": str(e),
                    },
                    exc_info=True,
                )
                failed += 1

                # Log the failure
                error_result = EmailSendResult(
                    success=False,
                    message_id=None,
                    error=str(e),
                    provider=self.email_service.provider_name,
                )
                self.send_log_repo.create_log_entry(
                    user_id=user.id,
                    email_address=user.email,
                    summary_date=summary_date,
                    ticker_count=len(summaries) if summaries else 0,
                    result=error_result,
                )

        return sent, failed

    def dispatch_daily_briefings(
        self,
        summary_date: date | None = None,
        batch_size: int = 50,
        max_users: int | None = None,
        dry_run: bool = False,
    ) -> DispatchStats:
        """Dispatch daily briefing emails to all eligible users.

        Args:
            summary_date: Target summary date (defaults to previous day)
            batch_size: Number of users to process per batch
            max_users: Maximum number of users to process (None = no limit)
            dry_run: If True, log but don't send

        Returns:
            DispatchStats with results
        """
        if summary_date is None:
            summary_date = date.today() - timedelta(days=1)

        logger.info(
            "Starting daily briefing dispatch",
            extra={
                "summary_date": summary_date.isoformat(),
                "batch_size": batch_size,
                "max_users": max_users,
                "dry_run": dry_run,
            },
        )

        # Get eligible users
        eligible_users = self.get_eligible_users()
        total_users = len(eligible_users)

        if max_users is not None:
            eligible_users = eligible_users[:max_users]
            total_users = len(eligible_users)

        logger.info(
            "Found eligible users",
            extra={"count": total_users},
        )

        # Filter to users with summaries
        users_with_summaries = self.filter_users_with_summaries(
            eligible_users, summary_date
        )

        logger.info(
            "Filtered to users with summaries",
            extra={
                "eligible_count": total_users,
                "with_summaries_count": len(users_with_summaries),
            },
        )

        # Process in batches
        sent = 0
        failed = 0
        skipped = total_users - len(users_with_summaries)

        for i in range(0, len(users_with_summaries), batch_size):
            batch = users_with_summaries[i : i + batch_size]
            batch_num = (i // batch_size) + 1
            total_batches = (len(users_with_summaries) + batch_size - 1) // batch_size

            logger.info(
                "Processing batch",
                extra={
                    "batch_num": batch_num,
                    "total_batches": total_batches,
                    "batch_size": len(batch),
                },
            )

            batch_sent, batch_failed = self.send_batch(
                batch, summary_date, dry_run=dry_run
            )
            sent += batch_sent
            failed += batch_failed

        stats = DispatchStats(
            total_users=total_users,
            sent=sent,
            skipped=skipped,
            failed=failed,
            dry_run=dry_run,
        )

        logger.info(
            "Dispatch completed",
            extra={
                "total_users": stats.total_users,
                "sent": stats.sent,
                "skipped": stats.skipped,
                "failed": stats.failed,
                "dry_run": stats.dry_run,
            },
        )

        return stats
