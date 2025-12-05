"""Unit tests for WeeklyDigestRepository."""

from datetime import UTC, date, datetime

from app.repos.weekly_digest_repo import WeeklyDigestRepository, get_iso_week_start


class TestGetIsoWeekStart:
    """Tests for ISO week start calculation."""

    def test_monday_returns_same_day(self) -> None:
        """Test that Monday returns itself."""
        monday = date(2025, 12, 1)
        assert get_iso_week_start(monday) == monday

    def test_wednesday_returns_monday(self) -> None:
        """Test that Wednesday returns Monday of same week."""
        wednesday = date(2025, 12, 3)
        monday = date(2025, 12, 1)
        assert get_iso_week_start(wednesday) == monday

    def test_sunday_returns_monday(self) -> None:
        """Test that Sunday returns Monday of same ISO week."""
        sunday = date(2025, 12, 7)
        monday = date(2025, 12, 1)
        assert get_iso_week_start(sunday) == monday

    def test_datetime_input(self) -> None:
        """Test that datetime input is handled correctly."""
        dt = datetime(2025, 12, 5, 14, 30, tzinfo=UTC)
        monday = date(2025, 12, 1)
        assert get_iso_week_start(dt) == monday


class TestWeeklyDigestRepository:
    """Tests for WeeklyDigestRepository."""

    def test_check_already_sent_returns_false_for_new(self, db_session) -> None:
        """Test that check_already_sent returns False when no record exists."""
        repo = WeeklyDigestRepository(db_session)
        result = repo.check_already_sent(user_id=1, week_start=date(2025, 12, 1))
        assert result is False

    def test_check_already_sent_returns_true_for_sent(self, db_session) -> None:
        """Test that check_already_sent returns True after marking sent."""
        repo = WeeklyDigestRepository(db_session)

        # Mark as sent
        repo.mark_sent(
            user_id=1,
            week_start=date(2025, 12, 1),
            message_id="ses-123",
            ticker_count=5,
            days_with_data=7,
        )
        db_session.commit()

        result = repo.check_already_sent(user_id=1, week_start=date(2025, 12, 1))
        assert result is True

    def test_check_already_sent_returns_true_for_skipped(self, db_session) -> None:
        """Test that check_already_sent returns True for skipped records."""
        repo = WeeklyDigestRepository(db_session)

        repo.mark_skipped(
            user_id=1,
            week_start=date(2025, 12, 1),
            skip_reason="no_data",
        )
        db_session.commit()

        result = repo.check_already_sent(user_id=1, week_start=date(2025, 12, 1))
        assert result is True

    def test_check_already_sent_returns_false_for_failed(self, db_session) -> None:
        """Test that check_already_sent returns False for failed records (can retry)."""
        repo = WeeklyDigestRepository(db_session)

        repo.mark_failed(
            user_id=1,
            week_start=date(2025, 12, 1),
            error="Connection error",
        )
        db_session.commit()

        result = repo.check_already_sent(user_id=1, week_start=date(2025, 12, 1))
        assert result is False

    def test_mark_sent_creates_record(self, db_session) -> None:
        """Test that mark_sent creates a record with correct status."""
        repo = WeeklyDigestRepository(db_session)

        record = repo.mark_sent(
            user_id=1,
            week_start=date(2025, 12, 1),
            message_id="ses-123",
            ticker_count=5,
            days_with_data=7,
        )
        db_session.commit()

        assert record is not None
        assert record.status == "sent"
        assert record.message_id == "ses-123"
        assert record.ticker_count == 5
        assert record.days_with_data == 7
        assert record.sent_at is not None

    def test_mark_failed_creates_record(self, db_session) -> None:
        """Test that mark_failed creates a record with error."""
        repo = WeeklyDigestRepository(db_session)

        record = repo.mark_failed(
            user_id=1,
            week_start=date(2025, 12, 1),
            error="API timeout",
            ticker_count=3,
        )
        db_session.commit()

        assert record is not None
        assert record.status == "failed"
        assert record.error == "API timeout"
        assert record.ticker_count == 3

    def test_mark_skipped_creates_record(self, db_session) -> None:
        """Test that mark_skipped creates a record with skip reason."""
        repo = WeeklyDigestRepository(db_session)

        record = repo.mark_skipped(
            user_id=1,
            week_start=date(2025, 12, 1),
            skip_reason="no_ticker_follows",
        )
        db_session.commit()

        assert record is not None
        assert record.status == "skipped"
        assert record.skip_reason == "no_ticker_follows"

    def test_get_user_history_returns_records(self, db_session) -> None:
        """Test that get_user_history returns user's records."""
        repo = WeeklyDigestRepository(db_session)

        # Create multiple records
        for week_offset in range(3):
            week_start = date(2025, 12, 1) - (week_offset * 7).__class__(
                days=week_offset * 7
            )
            repo.mark_sent(
                user_id=1,
                week_start=week_start,
                message_id=f"ses-{week_offset}",
                ticker_count=5,
                days_with_data=7,
            )
        db_session.commit()

        records, total = repo.get_user_history(user_id=1, limit=10)

        assert total == 3
        assert len(records) == 3

    def test_get_stats_for_week(self, db_session) -> None:
        """Test that get_stats_for_week returns correct statistics."""
        repo = WeeklyDigestRepository(db_session)
        week_start = date(2025, 12, 1)

        # Create various records
        for user_id in range(1, 4):
            repo.mark_sent(
                user_id=user_id,
                week_start=week_start,
                message_id=f"ses-{user_id}",
                ticker_count=5,
                days_with_data=7,
            )

        repo.mark_failed(
            user_id=4,
            week_start=week_start,
            error="Error",
        )

        repo.mark_skipped(
            user_id=5,
            week_start=week_start,
            skip_reason="no_data",
        )
        db_session.commit()

        stats = repo.get_stats_for_week(week_start)

        assert stats["total_eligible"] == 5
        assert stats["sent_count"] == 3
        assert stats["failed_count"] == 1
        assert stats["skipped_count"] == 1
        assert stats["success_rate"] == 0.6


class TestIdempotency:
    """Tests for idempotent delivery guarantees."""

    def test_unique_constraint_prevents_duplicates(self, db_session) -> None:
        """Test that unique constraint prevents duplicate records."""
        repo = WeeklyDigestRepository(db_session)
        week_start = date(2025, 12, 1)

        # First record
        repo.mark_sent(
            user_id=1,
            week_start=week_start,
            message_id="ses-1",
            ticker_count=5,
            days_with_data=7,
        )
        db_session.commit()

        # Second call should update, not create duplicate
        repo.mark_sent(
            user_id=1,
            week_start=week_start,
            message_id="ses-2",
            ticker_count=6,
            days_with_data=7,
        )
        db_session.commit()

        # Should still be only one record
        records, total = repo.get_user_history(user_id=1)
        assert total == 1
        assert records[0].message_id == "ses-2"
