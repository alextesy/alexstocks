"""Integration tests for email cadence API endpoints."""

from datetime import UTC, datetime
from unittest.mock import patch

import pytest

from app.db.models import User, UserProfile
from app.models.dto import EmailCadence


@pytest.fixture(autouse=True)
def setup_postgres_url(monkeypatch):
    """Set postgres URL before each test to satisfy config validation."""
    monkeypatch.setenv("DATABASE_URL", "postgresql://test:test@localhost:5432/test")


@pytest.fixture
def mock_auth():
    """Mock authentication to return a test user."""
    with patch("app.api.routes.users.get_current_user_id") as mock:
        mock.return_value = 1
        yield mock


@pytest.fixture
def test_user(db_session):
    """Create a test user in the database."""
    user = User(
        id=1,
        email="test@example.com",
        auth_provider="google",
        auth_provider_id="test-google-id",
        is_active=True,
        is_deleted=False,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    db_session.add(user)

    profile = UserProfile(
        user_id=1,
        timezone="UTC",
        preferences={"email_cadence": "daily_only"},
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    db_session.add(profile)
    db_session.commit()
    return user


class TestGetEmailCadence:
    """Tests for GET /api/users/me/email-cadence endpoint."""

    def test_get_email_cadence_returns_current_preference(
        self, db_session, test_user, mock_auth
    ) -> None:
        """Test that GET returns the user's current email cadence."""
        from app.repos.user_repo import UserRepository

        repo = UserRepository(db_session)
        cadence = repo.get_email_cadence(test_user.id)

        assert cadence == EmailCadence.DAILY_ONLY

    def test_get_email_cadence_default_for_new_user(
        self, db_session, mock_auth
    ) -> None:
        """Test that new users get default cadence."""
        # Create user without preferences
        user = User(
            id=2,
            email="new@example.com",
            auth_provider="google",
            auth_provider_id="test-google-id-2",
            is_active=True,
            is_deleted=False,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        db_session.add(user)

        profile = UserProfile(
            user_id=2,
            timezone="UTC",
            preferences={},
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        db_session.add(profile)
        db_session.commit()

        from app.repos.user_repo import UserRepository

        repo = UserRepository(db_session)
        cadence = repo.get_email_cadence(2)

        # Default for existing users is daily_only
        assert cadence == EmailCadence.DAILY_ONLY


class TestUpdateEmailCadence:
    """Tests for PUT /api/users/me/email-cadence endpoint."""

    def test_update_email_cadence_to_weekly_only(
        self, db_session, test_user, mock_auth
    ) -> None:
        """Test updating cadence to weekly_only."""
        from app.repos.user_repo import UserRepository

        repo = UserRepository(db_session)
        updated = repo.update_email_cadence(test_user.id, EmailCadence.WEEKLY_ONLY)
        db_session.commit()

        assert updated is True
        cadence = repo.get_email_cadence(test_user.id)
        assert cadence == EmailCadence.WEEKLY_ONLY

    def test_update_email_cadence_to_both(
        self, db_session, test_user, mock_auth
    ) -> None:
        """Test updating cadence to both."""
        from app.repos.user_repo import UserRepository

        repo = UserRepository(db_session)
        updated = repo.update_email_cadence(test_user.id, EmailCadence.BOTH)
        db_session.commit()

        assert updated is True
        cadence = repo.get_email_cadence(test_user.id)
        assert cadence == EmailCadence.BOTH

    def test_update_email_cadence_persists_across_sessions(
        self, db_session, test_user, mock_auth
    ) -> None:
        """Test that cadence preference persists."""
        from app.repos.user_repo import UserRepository

        repo = UserRepository(db_session)
        repo.update_email_cadence(test_user.id, EmailCadence.WEEKLY_ONLY)
        db_session.commit()

        # Expire the cache to simulate a new session
        db_session.expire_all()

        # Get fresh data
        cadence = repo.get_email_cadence(test_user.id)
        assert cadence == EmailCadence.WEEKLY_ONLY

    def test_update_email_cadence_invalid_user(self, db_session, mock_auth) -> None:
        """Test that updating non-existent user returns False."""
        from app.repos.user_repo import UserRepository

        repo = UserRepository(db_session)
        updated = repo.update_email_cadence(99999, EmailCadence.WEEKLY_ONLY)

        assert updated is False


class TestCadenceValidation:
    """Tests for email cadence validation."""

    def test_valid_cadence_values(self) -> None:
        """Test that valid cadence values are accepted."""
        assert EmailCadence("daily_only") == EmailCadence.DAILY_ONLY
        assert EmailCadence("weekly_only") == EmailCadence.WEEKLY_ONLY
        assert EmailCadence("both") == EmailCadence.BOTH

    def test_invalid_cadence_value_raises_error(self) -> None:
        """Test that invalid cadence values raise ValueError."""
        with pytest.raises(ValueError):
            EmailCadence("invalid")

        with pytest.raises(ValueError):
            EmailCadence("")

        # "none" is actually a valid cadence value
        assert EmailCadence("none") == EmailCadence.NONE


class TestCadenceFiltering:
    """Tests for filtering users by cadence."""

    def test_get_users_for_daily_email(self, db_session) -> None:
        """Test getting users who should receive daily emails."""
        from app.repos.user_repo import UserRepository

        # Create users with different cadences
        for i, cadence in enumerate(["daily_only", "weekly_only", "both"], start=10):
            user = User(
                id=i,
                email=f"user{i}@example.com",
                auth_provider="google",
                auth_provider_id=f"google-{i}",
                is_active=True,
                is_deleted=False,
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
            db_session.add(user)

            profile = UserProfile(
                user_id=i,
                timezone="UTC",
                preferences={"email_cadence": cadence},
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
            db_session.add(profile)

        db_session.commit()

        repo = UserRepository(db_session)

        # Check each user's cadence
        assert repo.get_email_cadence(10) == EmailCadence.DAILY_ONLY  # Should get daily
        assert (
            repo.get_email_cadence(11) == EmailCadence.WEEKLY_ONLY
        )  # Should NOT get daily
        assert repo.get_email_cadence(12) == EmailCadence.BOTH  # Should get daily

    def test_get_users_for_weekly_email(self, db_session) -> None:
        """Test getting users who should receive weekly emails."""
        from app.repos.user_repo import UserRepository

        # Create users with different cadences
        for i, cadence in enumerate(["daily_only", "weekly_only", "both"], start=20):
            user = User(
                id=i,
                email=f"user{i}@example.com",
                auth_provider="google",
                auth_provider_id=f"google-{i}",
                is_active=True,
                is_deleted=False,
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
            db_session.add(user)

            profile = UserProfile(
                user_id=i,
                timezone="UTC",
                preferences={"email_cadence": cadence},
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
            db_session.add(profile)

        db_session.commit()

        repo = UserRepository(db_session)

        # Check each user's cadence
        assert (
            repo.get_email_cadence(20) == EmailCadence.DAILY_ONLY
        )  # Should NOT get weekly
        assert (
            repo.get_email_cadence(21) == EmailCadence.WEEKLY_ONLY
        )  # Should get weekly
        assert repo.get_email_cadence(22) == EmailCadence.BOTH  # Should get weekly
