"""Unit tests for user deletion service."""

import logging
from unittest.mock import Mock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.models import (
    Base,
)
from app.models.dto import UserCreateDTO, UserProfileCreateDTO
from app.repos.user_repo import UserRepository
from app.services.slack_service import SlackService
from app.services.user_deletion_service import UserDeletionService


@pytest.fixture
def test_db_engine():
    """Create a test database engine."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    return engine


@pytest.fixture
def test_session(test_db_engine):
    """Create a test database session."""
    TestingSessionLocal = sessionmaker(
        autocommit=False, autoflush=False, bind=test_db_engine
    )
    session = TestingSessionLocal()
    yield session
    session.rollback()
    session.close()


@pytest.fixture
def test_user(test_session):
    """Create a test user."""
    repo = UserRepository(test_session)
    user_dto = UserCreateDTO(
        email="test@example.com",
        auth_provider="google",
        auth_provider_id="google_123",
    )
    user = repo.create_user(user_dto)
    test_session.commit()
    return user


@pytest.fixture
def test_user_with_related_data(test_session, test_user):
    """Create a test user with profile, notification channel, and ticker follow."""
    repo = UserRepository(test_session)

    # Create profile
    profile_dto = UserProfileCreateDTO(
        user_id=test_user.id,
        display_name="Test User",
        timezone="UTC",
    )
    repo.create_profile(profile_dto)

    # Create notification channel
    from app.models.dto import UserNotificationChannelCreateDTO

    channel_dto = UserNotificationChannelCreateDTO(
        user_id=test_user.id,
        channel_type="email",
        channel_value="test@example.com",
        is_verified=True,
        is_enabled=True,
    )
    repo.create_notification_channel(channel_dto)

    # Create ticker follow
    from app.models.dto import UserTickerFollowCreateDTO

    follow_dto = UserTickerFollowCreateDTO(
        user_id=test_user.id,
        ticker="AAPL",
    )
    repo.create_ticker_follow(follow_dto)

    test_session.commit()
    return test_user


@pytest.fixture
def slack_service():
    """Create a mock Slack service."""
    return Mock(spec=SlackService)


@pytest.fixture
def deletion_service(test_session, slack_service):
    """Create a UserDeletionService instance."""
    return UserDeletionService(db=test_session, slack_service=slack_service)


class TestUserDeletionService:
    """Test cases for UserDeletionService."""

    def test_delete_user_success(
        self, deletion_service, test_user_with_related_data, slack_service
    ):
        """Test successful user deletion."""
        user = test_user_with_related_data

        # Verify user exists before deletion
        repo = UserRepository(deletion_service.db)
        assert repo.get_user_by_id(user.id) is not None
        assert repo.get_profile(user.id) is not None
        assert len(repo.get_notification_channels(user.id)) > 0
        assert len(repo.get_ticker_follows(user.id)) > 0

        # Delete user
        result = deletion_service.delete_user(user.id, user.email)

        # Commit transaction
        deletion_service.db.commit()

        # Verify deletion succeeded
        assert result is True

        # Verify user is deleted
        assert repo.get_user_by_id(user.id, include_deleted=True) is None

        # Verify related data is deleted (CASCADE)
        assert repo.get_profile(user.id) is None
        assert len(repo.get_notification_channels(user.id)) == 0
        assert len(repo.get_ticker_follows(user.id)) == 0

        # Verify Slack notification was sent
        slack_service.notify_user_deleted.assert_called_once()
        call_args = slack_service.notify_user_deleted.call_args
        assert call_args[1]["user_id"] == user.id
        assert call_args[1]["email"] == user.email

    def test_delete_user_not_found(self, deletion_service, slack_service):
        """Test deletion when user does not exist."""
        result = deletion_service.delete_user(99999, "nonexistent@example.com")

        # Should return False for non-existent user
        assert result is False

        # Slack notification should not be sent
        slack_service.notify_user_deleted.assert_not_called()

    def test_delete_user_database_error_rollback(
        self, deletion_service, test_user, slack_service
    ):
        """Test that database errors trigger rollback."""
        # Mock hard_delete_user to raise an exception
        with patch.object(
            UserRepository, "hard_delete_user", side_effect=Exception("DB Error")
        ):
            # Attempt deletion
            result = deletion_service.delete_user(test_user.id, test_user.email)

            # Should return False on error
            assert result is False

            # Verify transaction was rolled back - user still exists
            repo = UserRepository(deletion_service.db)
            user_after = repo.get_user_by_id(test_user.id)
            assert user_after is not None
            assert user_after.id == test_user.id

            # Slack notification should not be sent
            slack_service.notify_user_deleted.assert_not_called()

    def test_delete_user_slack_notification_failure_handling(
        self, deletion_service, test_user_with_related_data, slack_service
    ):
        """Test that Slack notification failure doesn't prevent deletion."""
        user = test_user_with_related_data

        # Mock Slack notification to raise exception
        slack_service.notify_user_deleted.side_effect = Exception("Slack API Error")

        # Delete user (should succeed despite Slack failure)
        result = deletion_service.delete_user(user.id, user.email)

        # Commit transaction
        deletion_service.db.commit()

        # Deletion should still succeed
        assert result is True

        # Verify user is deleted
        repo = UserRepository(deletion_service.db)
        assert repo.get_user_by_id(user.id, include_deleted=True) is None

    def test_delete_user_audit_logging(
        self, deletion_service, test_user_with_related_data, slack_service, caplog
    ):
        """Test that deletion events are logged."""
        user = test_user_with_related_data

        with caplog.at_level(logging.INFO):
            deletion_service.delete_user(user.id, user.email)
            deletion_service.db.commit()

        # Verify deletion was logged
        log_messages = [record.message for record in caplog.records]
        assert any(
            "user_deletion" in msg.lower() or "deleted" in msg.lower()
            for msg in log_messages
        )
