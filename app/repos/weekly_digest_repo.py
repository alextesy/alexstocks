"""Repository for managing weekly digest send records."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import WeeklyDigestSendRecord
from app.models.dto import WeeklyDigestSendRecordDTO


def get_iso_week_start(dt: datetime | date) -> date:
    """Return Monday of the ISO week containing dt."""
    if isinstance(dt, datetime):
        dt = dt.date()
    return dt - timedelta(days=dt.weekday())


class WeeklyDigestRepository:
    """Data-access helpers for :class:`WeeklyDigestSendRecord`."""

    def __init__(self, session: Session) -> None:
        """Initialize the repository with a database session."""
        self.session = session

    def get_record_for_user_week(
        self, user_id: int, week_start: date
    ) -> WeeklyDigestSendRecordDTO | None:
        """Get the weekly digest record for a specific user and week."""
        stmt = select(WeeklyDigestSendRecord).where(
            WeeklyDigestSendRecord.user_id == user_id,
            WeeklyDigestSendRecord.week_start_date == week_start,
        )
        entity = self.session.execute(stmt).scalar_one_or_none()
        return self._to_dto(entity) if entity else None

    def check_already_sent(self, user_id: int, week_start: date) -> bool:
        """Check if a digest was already sent for this user and week."""
        stmt = select(WeeklyDigestSendRecord).where(
            WeeklyDigestSendRecord.user_id == user_id,
            WeeklyDigestSendRecord.week_start_date == week_start,
            WeeklyDigestSendRecord.status.in_(["sent", "skipped"]),
        )
        return self.session.execute(stmt).scalar_one_or_none() is not None

    def create_pending(
        self, user_id: int, week_start: date
    ) -> WeeklyDigestSendRecordDTO:
        """Create a pending record for a user and week."""
        now = datetime.now(UTC)
        entity = WeeklyDigestSendRecord(
            user_id=user_id,
            week_start_date=week_start,
            status="pending",
            created_at=now,
        )
        self.session.add(entity)
        self.session.flush()
        return self._to_dto(entity)

    def mark_sent(
        self,
        user_id: int,
        week_start: date,
        message_id: str | None,
        ticker_count: int,
        days_with_data: int,
    ) -> WeeklyDigestSendRecordDTO | None:
        """Mark a record as sent."""
        stmt = select(WeeklyDigestSendRecord).where(
            WeeklyDigestSendRecord.user_id == user_id,
            WeeklyDigestSendRecord.week_start_date == week_start,
        )
        entity = self.session.execute(stmt).scalar_one_or_none()
        if not entity:
            # Create new record if not exists
            entity = WeeklyDigestSendRecord(
                user_id=user_id,
                week_start_date=week_start,
                created_at=datetime.now(UTC),
            )
            self.session.add(entity)

        entity.status = "sent"
        entity.message_id = message_id
        entity.ticker_count = ticker_count
        entity.days_with_data = days_with_data
        entity.sent_at = datetime.now(UTC)
        entity.error = None
        entity.skip_reason = None
        self.session.flush()
        return self._to_dto(entity)

    def mark_failed(
        self,
        user_id: int,
        week_start: date,
        error: str,
        ticker_count: int = 0,
        days_with_data: int = 0,
    ) -> WeeklyDigestSendRecordDTO | None:
        """Mark a record as failed."""
        stmt = select(WeeklyDigestSendRecord).where(
            WeeklyDigestSendRecord.user_id == user_id,
            WeeklyDigestSendRecord.week_start_date == week_start,
        )
        entity = self.session.execute(stmt).scalar_one_or_none()
        if not entity:
            entity = WeeklyDigestSendRecord(
                user_id=user_id,
                week_start_date=week_start,
                created_at=datetime.now(UTC),
            )
            self.session.add(entity)

        entity.status = "failed"
        entity.error = error
        entity.ticker_count = ticker_count
        entity.days_with_data = days_with_data
        entity.skip_reason = None
        self.session.flush()
        return self._to_dto(entity)

    def mark_skipped(
        self,
        user_id: int,
        week_start: date,
        skip_reason: str,
    ) -> WeeklyDigestSendRecordDTO | None:
        """Mark a record as skipped with a reason."""
        stmt = select(WeeklyDigestSendRecord).where(
            WeeklyDigestSendRecord.user_id == user_id,
            WeeklyDigestSendRecord.week_start_date == week_start,
        )
        entity = self.session.execute(stmt).scalar_one_or_none()
        if not entity:
            entity = WeeklyDigestSendRecord(
                user_id=user_id,
                week_start_date=week_start,
                created_at=datetime.now(UTC),
            )
            self.session.add(entity)

        entity.status = "skipped"
        entity.skip_reason = skip_reason
        entity.error = None
        entity.ticker_count = 0
        entity.days_with_data = 0
        self.session.flush()
        return self._to_dto(entity)

    def get_records_for_week(self, week_start: date) -> list[WeeklyDigestSendRecordDTO]:
        """Get all records for a specific week."""
        stmt = (
            select(WeeklyDigestSendRecord)
            .where(WeeklyDigestSendRecord.week_start_date == week_start)
            .order_by(WeeklyDigestSendRecord.created_at.desc())
        )
        entities = self.session.execute(stmt).scalars().all()
        return [self._to_dto(e) for e in entities]

    def get_user_history(
        self,
        user_id: int,
        limit: int = 10,
        offset: int = 0,
    ) -> tuple[list[WeeklyDigestSendRecordDTO], int]:
        """Get weekly digest history for a user with pagination."""
        # Count total
        count_stmt = select(func.count(WeeklyDigestSendRecord.id)).where(
            WeeklyDigestSendRecord.user_id == user_id
        )
        total = self.session.execute(count_stmt).scalar_one()

        # Get records
        stmt = (
            select(WeeklyDigestSendRecord)
            .where(WeeklyDigestSendRecord.user_id == user_id)
            .order_by(WeeklyDigestSendRecord.week_start_date.desc())
            .limit(limit)
            .offset(offset)
        )
        entities = self.session.execute(stmt).scalars().all()
        return [self._to_dto(e) for e in entities], total

    def get_stats_for_week(self, week_start: date) -> dict:
        """Get statistics for a specific week's digest run."""
        stmt = select(WeeklyDigestSendRecord).where(
            WeeklyDigestSendRecord.week_start_date == week_start
        )
        entities = self.session.execute(stmt).scalars().all()

        total = len(entities)
        sent = sum(1 for e in entities if e.status == "sent")
        failed = sum(1 for e in entities if e.status == "failed")
        skipped = sum(1 for e in entities if e.status == "skipped")
        pending = sum(1 for e in entities if e.status == "pending")

        return {
            "week_start_date": week_start,
            "total_eligible": total,
            "sent_count": sent,
            "failed_count": failed,
            "skipped_count": skipped,
            "pending_count": pending,
            "success_rate": sent / total if total > 0 else 0.0,
        }

    @staticmethod
    def _to_dto(entity: WeeklyDigestSendRecord) -> WeeklyDigestSendRecordDTO:
        return WeeklyDigestSendRecordDTO(
            id=entity.id,
            user_id=entity.user_id,
            week_start_date=entity.week_start_date,
            status=entity.status,
            ticker_count=entity.ticker_count,
            days_with_data=entity.days_with_data,
            message_id=entity.message_id,
            error=entity.error,
            skip_reason=entity.skip_reason,
            created_at=entity.created_at,
            sent_at=entity.sent_at,
        )
