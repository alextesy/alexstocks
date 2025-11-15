"""Repository for managing email send logs."""

from __future__ import annotations

import logging
from datetime import UTC, date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import Integer, func, select
from sqlalchemy.orm import Session

from app.db.models import EmailSendLog

if TYPE_CHECKING:
    from app.models.dto import EmailSendResult

logger = logging.getLogger(__name__)


class EmailSendLogRepository:
    """Repository for email send log operations."""

    def __init__(self, session: Session):
        """Initialize repository with database session."""
        self.session = session

    def create_log_entry(
        self,
        user_id: int,
        email_address: str,
        summary_date: date,
        ticker_count: int,
        result: EmailSendResult,
    ) -> EmailSendLog:
        """Create a log entry for an email send attempt.

        Args:
            user_id: User ID who received the email
            email_address: Email address (denormalized)
            summary_date: Date of the summary
            ticker_count: Number of tickers in the email
            result: EmailSendResult from the send operation

        Returns:
            Created EmailSendLog entry
        """
        log_entry = EmailSendLog(
            user_id=user_id,
            email_address=email_address,
            summary_date=summary_date,
            ticker_count=ticker_count,
            success=result.success,
            message_id=result.message_id,
            error=result.error,
            provider=result.provider,
            sent_at=datetime.now(UTC),
        )
        self.session.add(log_entry)
        self.session.flush()
        return log_entry

    def get_user_sends_for_date(
        self, user_id: int, summary_date: date
    ) -> list[EmailSendLog]:
        """Check if user already received email for a given date.

        Args:
            user_id: User ID to check
            summary_date: Summary date to check

        Returns:
            List of send log entries for this user/date
        """
        stmt = select(EmailSendLog).where(
            EmailSendLog.user_id == user_id,
            EmailSendLog.summary_date == summary_date,
        )
        return list(self.session.execute(stmt).scalars().all())

    def get_send_stats(
        self,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> dict[str, int]:
        """Get aggregate statistics for email sends.

        Args:
            start_date: Optional start date filter
            end_date: Optional end date filter

        Returns:
            Dictionary with stats: total, successful, failed
        """
        stmt = select(
            func.count(EmailSendLog.id).label("total"),
            func.sum(func.cast(EmailSendLog.success, Integer)).label("successful"),
        ).select_from(EmailSendLog)

        if start_date:
            stmt = stmt.where(EmailSendLog.summary_date >= start_date)
        if end_date:
            stmt = stmt.where(EmailSendLog.summary_date <= end_date)

        result = self.session.execute(stmt).one()
        total = result.total or 0
        successful = result.successful or 0
        failed = total - successful

        return {
            "total": total,
            "successful": successful,
            "failed": failed,
        }
