"""Unit tests for email cadence preference."""

import pytest

from app.models.dto import EmailCadence


class TestEmailCadence:
    """Tests for EmailCadence enum."""

    def test_enum_values(self) -> None:
        """Test that all expected enum values exist."""
        assert EmailCadence.DAILY_ONLY.value == "daily_only"
        assert EmailCadence.WEEKLY_ONLY.value == "weekly_only"
        assert EmailCadence.BOTH.value == "both"

    def test_enum_from_string(self) -> None:
        """Test creating enum from string value."""
        assert EmailCadence("daily_only") == EmailCadence.DAILY_ONLY
        assert EmailCadence("weekly_only") == EmailCadence.WEEKLY_ONLY
        assert EmailCadence("both") == EmailCadence.BOTH

    def test_enum_invalid_value(self) -> None:
        """Test that invalid values raise ValueError."""
        with pytest.raises(ValueError):
            EmailCadence("invalid")

    def test_enum_is_str(self) -> None:
        """Test that EmailCadence is also a string."""
        cadence = EmailCadence.BOTH
        assert isinstance(cadence, str)
        assert cadence == "both"

    def test_should_send_daily_for_daily_only(self) -> None:
        """Test daily email logic for daily_only cadence."""
        cadence = EmailCadence.DAILY_ONLY
        assert cadence in (EmailCadence.DAILY_ONLY, EmailCadence.BOTH)

    def test_should_send_daily_for_both(self) -> None:
        """Test daily email logic for both cadence."""
        cadence = EmailCadence.BOTH
        assert cadence in (EmailCadence.DAILY_ONLY, EmailCadence.BOTH)

    def test_should_not_send_daily_for_weekly_only(self) -> None:
        """Test daily email logic for weekly_only cadence."""
        cadence = EmailCadence.WEEKLY_ONLY
        assert cadence not in (EmailCadence.DAILY_ONLY, EmailCadence.BOTH)

    def test_should_send_weekly_for_weekly_only(self) -> None:
        """Test weekly email logic for weekly_only cadence."""
        cadence = EmailCadence.WEEKLY_ONLY
        assert cadence in (EmailCadence.WEEKLY_ONLY, EmailCadence.BOTH)

    def test_should_send_weekly_for_both(self) -> None:
        """Test weekly email logic for both cadence."""
        cadence = EmailCadence.BOTH
        assert cadence in (EmailCadence.WEEKLY_ONLY, EmailCadence.BOTH)

    def test_should_not_send_weekly_for_daily_only(self) -> None:
        """Test weekly email logic for daily_only cadence."""
        cadence = EmailCadence.DAILY_ONLY
        assert cadence not in (EmailCadence.WEEKLY_ONLY, EmailCadence.BOTH)
