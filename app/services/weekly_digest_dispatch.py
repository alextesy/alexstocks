"""Weekly digest dispatch service for batch sending weekly emails."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import date

from sqlalchemy.orm import Session

from app.models.dto import (
    UserDTO,
)
from app.repos.user_repo import UserRepository
from app.repos.weekly_digest_repo import WeeklyDigestRepository
from app.services.email_service import EmailService
from app.services.email_utils import generate_unsubscribe_token
from app.services.weekly_summary import WeeklySummaryService, get_week_boundaries

logger = logging.getLogger(__name__)


@dataclass
class WeeklyDispatchStats:
    """Statistics from a weekly dispatch run."""

    week_start: date
    week_end: date
    total_eligible: int
    sent: int
    skipped: int
    failed: int
    dry_run: bool


class WeeklyDigestDispatchService:
    """Service for dispatching weekly digest emails to users."""

    def __init__(
        self,
        session: Session,
        email_service: EmailService,
        user_repo: UserRepository | None = None,
        digest_repo: WeeklyDigestRepository | None = None,
        summary_service: WeeklySummaryService | None = None,
    ):
        """Initialize dispatch service.

        Args:
            session: Database session
            email_service: Email service for sending emails
            user_repo: User repository (created if not provided)
            digest_repo: Weekly digest repository (created if not provided)
            summary_service: Weekly summary service (created if not provided)
        """
        self.session = session
        self.email_service = email_service
        self.user_repo = user_repo or UserRepository(session)
        self.digest_repo = digest_repo or WeeklyDigestRepository(session)
        self.summary_service = summary_service or WeeklySummaryService(session)

    def get_eligible_users(self) -> list[UserDTO]:
        """Get all users eligible for weekly digest emails.

        Returns:
            List of users with weekly cadence enabled
        """
        return self.user_repo.get_users_with_weekly_digest_enabled()

    def _get_sample_tickers_for_testing(self) -> list[str]:
        """Get sample tickers for testing when user has no follows.

        Returns:
            List of popular ticker symbols
        """
        # Get tickers that have recent data in the database
        from sqlalchemy import func, select

        from app.db.models import DailyTickerSummary

        stmt = (
            select(DailyTickerSummary.ticker)
            .group_by(DailyTickerSummary.ticker)
            .order_by(func.count().desc())
            .limit(5)
        )
        result = self.session.execute(stmt).scalars().all()

        if result:
            return list(result)

        # Fallback to well-known tickers
        return ["AAPL", "TSLA", "NVDA", "MSFT", "GOOGL"]

    def dispatch_weekly_digests(
        self,
        week_start: date | None = None,
        week_end: date | None = None,
        batch_size: int = 100,
        max_users: int | None = None,
        dry_run: bool = False,
        single_user_email: str | None = None,
        force: bool = False,
    ) -> WeeklyDispatchStats:
        """Dispatch weekly digest emails to all eligible users.

        Args:
            week_start: Start of week (Monday). Defaults to previous week.
            week_end: End of week (Sunday). Defaults to previous week.
            batch_size: Number of users to process per batch
            max_users: Maximum number of users to process (None = no limit)
            dry_run: If True, log but don't send
            single_user_email: If provided, only send to this user
            force: If True, bypass idempotency checks (for testing)

        Returns:
            WeeklyDispatchStats with results
        """
        # Determine week boundaries
        if week_start is None or week_end is None:
            boundaries = get_week_boundaries()
            week_start = week_start or boundaries.week_start
            week_end = week_end or boundaries.week_end

        logger.info(
            "Starting weekly digest dispatch",
            extra={
                "week_start": week_start.isoformat(),
                "week_end": week_end.isoformat(),
                "batch_size": batch_size,
                "max_users": max_users,
                "dry_run": dry_run,
                "single_user_email": single_user_email,
                "force": force,
            },
        )

        # Get eligible users
        if single_user_email:
            # Single user mode for testing
            user = self.user_repo.get_user_by_email(single_user_email)
            if not user:
                logger.warning(
                    "User not found for single-user dispatch",
                    extra={"email": single_user_email},
                )
                return WeeklyDispatchStats(
                    week_start=week_start,
                    week_end=week_end,
                    total_eligible=0,
                    sent=0,
                    skipped=0,
                    failed=0,
                    dry_run=dry_run,
                )
            eligible_users = [user]
        else:
            eligible_users = self.get_eligible_users()

        total_eligible = len(eligible_users)

        if max_users is not None:
            eligible_users = eligible_users[:max_users]
            total_eligible = len(eligible_users)

        logger.info(
            "Found eligible users",
            extra={"count": total_eligible},
        )

        # Process users
        sent = 0
        skipped = 0
        failed = 0
        rate_limit_delay = 1.0 / 14.0  # 14 emails per second

        for idx, user in enumerate(eligible_users):
            try:
                result = self._process_user(
                    user=user,
                    week_start=week_start,
                    week_end=week_end,
                    dry_run=dry_run,
                    force=force,
                )

                if result == "sent":
                    sent += 1
                elif result == "skipped":
                    skipped += 1
                else:
                    failed += 1

                # Rate limiting
                if not dry_run and idx < len(eligible_users) - 1:
                    time.sleep(rate_limit_delay)

            except Exception as e:
                logger.error(
                    "Error processing user for weekly digest",
                    extra={
                        "user_id": user.id,
                        "user_email": user.email,
                        "error": str(e),
                    },
                    exc_info=True,
                )
                failed += 1

                # Record failure
                try:
                    self.digest_repo.mark_failed(
                        user_id=user.id,
                        week_start=week_start,
                        error=str(e),
                    )
                    self.session.commit()
                except Exception:
                    pass

        stats = WeeklyDispatchStats(
            week_start=week_start,
            week_end=week_end,
            total_eligible=total_eligible,
            sent=sent,
            skipped=skipped,
            failed=failed,
            dry_run=dry_run,
        )

        logger.info(
            "Weekly digest dispatch completed",
            extra={
                "week_start": stats.week_start.isoformat(),
                "week_end": stats.week_end.isoformat(),
                "total_eligible": stats.total_eligible,
                "sent": stats.sent,
                "skipped": stats.skipped,
                "failed": stats.failed,
                "dry_run": stats.dry_run,
            },
        )

        return stats

    def _process_user(
        self,
        user: UserDTO,
        week_start: date,
        week_end: date,
        dry_run: bool,
        force: bool = False,
    ) -> str:
        """Process a single user for weekly digest.

        Args:
            user: User to process
            week_start: Start of week
            week_end: End of week
            dry_run: If True, don't actually send
            force: If True, bypass idempotency and skip checks (for testing)

        Returns:
            "sent", "skipped", or "failed"
        """
        # Check idempotency - already sent? (bypass if force=True)
        if not force and self.digest_repo.check_already_sent(user.id, week_start):
            logger.debug(
                "Skipping user - digest already sent",
                extra={"user_id": user.id, "week_start": week_start.isoformat()},
            )
            return "skipped"

        # Get user's followed tickers
        follows = self.user_repo.get_ticker_follows(user.id)
        if not follows:
            if force:
                logger.warning(
                    "Force mode: user has no ticker follows, using sample tickers",
                    extra={"user_id": user.id},
                )
                # Use sample tickers for testing
                follows = []
            else:
                logger.debug(
                    "Skipping user - no ticker follows",
                    extra={"user_id": user.id},
                )
                self.digest_repo.mark_skipped(
                    user_id=user.id,
                    week_start=week_start,
                    skip_reason="no_ticker_follows",
                )
                self.session.commit()
                return "skipped"

        tickers = [f.ticker.upper() for f in follows] if follows else []

        # In force mode with no tickers, get some popular tickers for testing
        if force and not tickers:
            tickers = self._get_sample_tickers_for_testing()
            logger.info(
                "Force mode: using sample tickers for testing",
                extra={"user_id": user.id, "sample_tickers": tickers},
            )

        # Aggregate weekly summaries
        aggregates = self.summary_service.aggregate_weekly_summaries(
            tickers=tickers,
            week_start=week_start,
            week_end=week_end,
        )

        if not aggregates:
            if force:
                logger.warning(
                    "Force mode: no weekly data for tickers, sending empty digest",
                    extra={"user_id": user.id, "tickers": tickers},
                )
                # Continue with empty aggregates - will get fallback content
            else:
                logger.debug(
                    "Skipping user - no weekly data for tickers",
                    extra={"user_id": user.id, "tickers": tickers},
                )
                self.digest_repo.mark_skipped(
                    user_id=user.id,
                    week_start=week_start,
                    skip_reason="no_weekly_data",
                )
                self.session.commit()
                return "skipped"

        # Get user profile
        profile = self.user_repo.get_profile(user.id)
        user_timezone = profile.timezone if profile else "UTC"

        # Generate digest content
        digest_content = self.summary_service.generate_weekly_digest(
            aggregates=aggregates,
            week_start=week_start,
            week_end=week_end,
            user_timezone=user_timezone,
        )

        if dry_run:
            logger.info(
                "DRY RUN: Would send weekly digest",
                extra={
                    "user_id": user.id,
                    "user_email": user.email,
                    "ticker_count": digest_content.total_tickers,
                    "days_with_data": digest_content.days_with_data,
                },
            )
            return "sent"

        # Send email
        unsubscribe_token = generate_unsubscribe_token(user.id)
        result = self.email_service.send_weekly_digest(
            user=user,
            digest_content=digest_content,
            user_profile=profile,
            unsubscribe_token=unsubscribe_token,
        )

        if result.success:
            self.digest_repo.mark_sent(
                user_id=user.id,
                week_start=week_start,
                message_id=result.message_id,
                ticker_count=digest_content.total_tickers,
                days_with_data=digest_content.days_with_data,
            )
            self.session.commit()
            return "sent"
        else:
            self.digest_repo.mark_failed(
                user_id=user.id,
                week_start=week_start,
                error=result.error or "Unknown error",
                ticker_count=digest_content.total_tickers,
                days_with_data=digest_content.days_with_data,
            )
            self.session.commit()
            return "failed"
