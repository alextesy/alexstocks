"""Tests for user repository."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.models import Base, Ticker
from app.models.dto import (
    UserCreateDTO,
    UserNotificationChannelCreateDTO,
    UserProfileCreateDTO,
    UserTickerFollowCreateDTO,
)
from app.repos.user_repo import UserRepository


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
def user_repo(test_session):
    """Create a UserRepository instance."""
    return UserRepository(test_session)


@pytest.fixture
def sample_ticker(test_session):
    """Create a sample ticker."""
    ticker = Ticker(symbol="AAPL", name="Apple Inc.")
    test_session.add(ticker)
    test_session.commit()
    return ticker


# User CRUD Tests


def test_create_user(user_repo):
    """Test creating a user."""
    user_dto = UserCreateDTO(
        email="test@example.com",
        auth_provider="google",
        auth_provider_id="google_123",
    )
    created = user_repo.create_user(user_dto)

    assert created.id is not None
    assert created.email == "test@example.com"
    assert created.auth_provider == "google"
    assert created.auth_provider_id == "google_123"
    assert created.is_active is True
    assert created.is_deleted is False
    assert created.deleted_at is None


def test_create_user_validates_email():
    """Test that creating a user validates email."""
    with pytest.raises(ValueError, match="Valid email is required"):
        UserCreateDTO(email="invalid-email")


def test_get_user_by_id(user_repo):
    """Test getting user by ID."""
    # Create user
    user_dto = UserCreateDTO(email="test@example.com")
    created = user_repo.create_user(user_dto)

    # Get user
    retrieved = user_repo.get_user_by_id(created.id)
    assert retrieved is not None
    assert retrieved.id == created.id
    assert retrieved.email == created.email


def test_get_user_by_id_excludes_deleted(user_repo):
    """Test that get_user_by_id excludes deleted users by default."""
    # Create and soft delete user
    user_dto = UserCreateDTO(email="test@example.com")
    created = user_repo.create_user(user_dto)
    user_repo.soft_delete_user(created.id)

    # Should not find deleted user by default
    retrieved = user_repo.get_user_by_id(created.id)
    assert retrieved is None

    # Should find with include_deleted=True
    retrieved = user_repo.get_user_by_id(created.id, include_deleted=True)
    assert retrieved is not None
    assert retrieved.is_deleted is True


def test_get_user_by_email(user_repo):
    """Test getting user by email."""
    user_dto = UserCreateDTO(email="test@example.com")
    created = user_repo.create_user(user_dto)

    retrieved = user_repo.get_user_by_email("test@example.com")
    assert retrieved is not None
    assert retrieved.id == created.id


def test_get_user_by_auth_provider_id(user_repo):
    """Test getting user by OAuth provider ID."""
    user_dto = UserCreateDTO(email="test@example.com", auth_provider_id="google_123")
    created = user_repo.create_user(user_dto)

    retrieved = user_repo.get_user_by_auth_provider_id("google_123")
    assert retrieved is not None
    assert retrieved.id == created.id


def test_list_users(user_repo):
    """Test listing users with pagination."""
    # Create multiple users
    for i in range(5):
        user_dto = UserCreateDTO(email=f"user{i}@example.com")
        user_repo.create_user(user_dto)

    # List all users
    users = user_repo.list_users(limit=10)
    assert len(users) == 5

    # Test pagination
    page1 = user_repo.list_users(limit=2, offset=0)
    page2 = user_repo.list_users(limit=2, offset=2)
    assert len(page1) == 2
    assert len(page2) == 2
    assert page1[0].id != page2[0].id


def test_update_user(user_repo):
    """Test updating user fields."""
    user_dto = UserCreateDTO(email="test@example.com")
    created = user_repo.create_user(user_dto)

    # Update user
    updated = user_repo.update_user(created.id, is_active=False)
    assert updated is not None
    assert updated.is_active is False


def test_soft_delete_user(user_repo):
    """Test soft deleting a user."""
    user_dto = UserCreateDTO(email="test@example.com")
    created = user_repo.create_user(user_dto)

    # Soft delete
    result = user_repo.soft_delete_user(created.id)
    assert result is True

    # Verify user is soft deleted
    user = user_repo.get_user_by_id(created.id, include_deleted=True)
    assert user is not None
    assert user.is_deleted is True
    assert user.is_active is False
    assert user.deleted_at is not None


def test_restore_user(user_repo):
    """Test restoring a soft-deleted user."""
    user_dto = UserCreateDTO(email="test@example.com")
    created = user_repo.create_user(user_dto)

    # Soft delete then restore
    user_repo.soft_delete_user(created.id)
    result = user_repo.restore_user(created.id)
    assert result is True

    # Verify user is restored
    user = user_repo.get_user_by_id(created.id)
    assert user is not None
    assert user.is_deleted is False
    assert user.is_active is True
    assert user.deleted_at is None


def test_hard_delete_user(user_repo):
    """Test permanently deleting a user."""
    user_dto = UserCreateDTO(email="test@example.com")
    created = user_repo.create_user(user_dto)

    # Hard delete
    result = user_repo.hard_delete_user(created.id)
    assert result is True

    # Verify user is gone
    user = user_repo.get_user_by_id(created.id, include_deleted=True)
    assert user is None


# UserProfile Tests


def test_create_profile(user_repo):
    """Test creating a user profile."""
    # Create user first
    user_dto = UserCreateDTO(email="test@example.com")
    user = user_repo.create_user(user_dto)

    # Create profile
    profile_dto = UserProfileCreateDTO(
        user_id=user.id,
        display_name="Test User",
        timezone="America/New_York",
        bio="Test bio",
    )
    profile = user_repo.create_profile(profile_dto)

    assert profile.user_id == user.id
    assert profile.display_name == "Test User"
    assert profile.timezone == "America/New_York"
    assert profile.bio == "Test bio"


def test_update_profile(user_repo):
    """Test updating an existing profile."""
    # Create user and profile
    user_dto = UserCreateDTO(email="test@example.com")
    user = user_repo.create_user(user_dto)

    profile_dto = UserProfileCreateDTO(user_id=user.id, display_name="Original Name")
    user_repo.create_profile(profile_dto)

    # Update profile
    updated_dto = UserProfileCreateDTO(user_id=user.id, display_name="Updated Name")
    updated = user_repo.create_profile(updated_dto)

    assert updated.display_name == "Updated Name"


def test_get_profile(user_repo):
    """Test getting a user profile."""
    user_dto = UserCreateDTO(email="test@example.com")
    user = user_repo.create_user(user_dto)

    profile_dto = UserProfileCreateDTO(user_id=user.id, display_name="Test User")
    user_repo.create_profile(profile_dto)

    retrieved = user_repo.get_profile(user.id)
    assert retrieved is not None
    assert retrieved.user_id == user.id


# UserNotificationChannel Tests


def test_create_notification_channel(user_repo):
    """Test creating a notification channel."""
    user_dto = UserCreateDTO(email="test@example.com")
    user = user_repo.create_user(user_dto)

    channel_dto = UserNotificationChannelCreateDTO(
        user_id=user.id, channel_type="email", channel_value="test@example.com"
    )
    channel = user_repo.create_notification_channel(channel_dto)

    assert channel.user_id == user.id
    assert channel.channel_type == "email"
    assert channel.channel_value == "test@example.com"
    assert channel.is_verified is False
    assert channel.is_enabled is True


def test_create_notification_channel_validates_type():
    """Test that channel type is validated."""
    with pytest.raises(ValueError, match="channel_type must be one of"):
        UserNotificationChannelCreateDTO(
            user_id=1, channel_type="invalid", channel_value="test"
        )


def test_get_notification_channels(user_repo):
    """Test getting all notification channels for a user."""
    user_dto = UserCreateDTO(email="test@example.com")
    user = user_repo.create_user(user_dto)

    # Create multiple channels
    email_dto = UserNotificationChannelCreateDTO(
        user_id=user.id, channel_type="email", channel_value="test@example.com"
    )
    sms_dto = UserNotificationChannelCreateDTO(
        user_id=user.id, channel_type="sms", channel_value="+1234567890"
    )
    user_repo.create_notification_channel(email_dto)
    user_repo.create_notification_channel(sms_dto)

    channels = user_repo.get_notification_channels(user.id)
    assert len(channels) == 2
    assert any(ch.channel_type == "email" for ch in channels)
    assert any(ch.channel_type == "sms" for ch in channels)


def test_update_notification_channel(user_repo):
    """Test updating a notification channel."""
    user_dto = UserCreateDTO(email="test@example.com")
    user = user_repo.create_user(user_dto)

    channel_dto = UserNotificationChannelCreateDTO(
        user_id=user.id, channel_type="email", channel_value="test@example.com"
    )
    channel = user_repo.create_notification_channel(channel_dto)

    # Update channel
    updated = user_repo.update_notification_channel(
        channel.id, is_enabled=False, is_verified=True
    )
    assert updated is not None
    assert updated.is_enabled is False
    assert updated.is_verified is True


def test_delete_notification_channel(user_repo):
    """Test deleting a notification channel."""
    user_dto = UserCreateDTO(email="test@example.com")
    user = user_repo.create_user(user_dto)

    channel_dto = UserNotificationChannelCreateDTO(
        user_id=user.id, channel_type="email", channel_value="test@example.com"
    )
    channel = user_repo.create_notification_channel(channel_dto)

    result = user_repo.delete_notification_channel(channel.id)
    assert result is True

    channels = user_repo.get_notification_channels(user.id)
    assert len(channels) == 0


# UserTickerFollow Tests


def test_create_ticker_follow(user_repo, sample_ticker):
    """Test creating a ticker follow."""
    user_dto = UserCreateDTO(email="test@example.com")
    user = user_repo.create_user(user_dto)

    follow_dto = UserTickerFollowCreateDTO(
        user_id=user.id, ticker="AAPL", notify_on_signals=True
    )
    follow = user_repo.create_ticker_follow(follow_dto)

    assert follow.user_id == user.id
    assert follow.ticker == "AAPL"
    assert follow.notify_on_signals is True
    assert follow.notify_on_price_change is False


def test_create_ticker_follow_validates_ticker():
    """Test that ticker is validated."""
    with pytest.raises(ValueError, match="ticker is required"):
        UserTickerFollowCreateDTO(user_id=1, ticker="")


def test_create_ticker_follow_validates_threshold():
    """Test that price change threshold is validated."""
    with pytest.raises(ValueError, match="price_change_threshold must be positive"):
        UserTickerFollowCreateDTO(user_id=1, ticker="AAPL", price_change_threshold=-1.0)


def test_create_ticker_follow_updates_existing(user_repo, sample_ticker):
    """Test that creating a duplicate follow updates the existing one."""
    user_dto = UserCreateDTO(email="test@example.com")
    user = user_repo.create_user(user_dto)

    # Create initial follow
    follow_dto1 = UserTickerFollowCreateDTO(
        user_id=user.id, ticker="AAPL", notify_on_signals=True
    )
    follow1 = user_repo.create_ticker_follow(follow_dto1)

    # Create duplicate (should update)
    follow_dto2 = UserTickerFollowCreateDTO(
        user_id=user.id, ticker="AAPL", notify_on_signals=False
    )
    follow2 = user_repo.create_ticker_follow(follow_dto2)

    # Should have same ID (updated, not created new)
    assert follow1.id == follow2.id
    assert follow2.notify_on_signals is False


def test_get_ticker_follows(user_repo, sample_ticker):
    """Test getting all ticker follows for a user."""
    user_dto = UserCreateDTO(email="test@example.com")
    user = user_repo.create_user(user_dto)

    # Create a follow
    follow_dto = UserTickerFollowCreateDTO(user_id=user.id, ticker="AAPL")
    user_repo.create_ticker_follow(follow_dto)

    follows = user_repo.get_ticker_follows(user.id)
    assert len(follows) == 1
    assert follows[0].ticker == "AAPL"


def test_get_ticker_follow(user_repo, sample_ticker):
    """Test getting a specific ticker follow."""
    user_dto = UserCreateDTO(email="test@example.com")
    user = user_repo.create_user(user_dto)

    follow_dto = UserTickerFollowCreateDTO(user_id=user.id, ticker="AAPL")
    user_repo.create_ticker_follow(follow_dto)

    follow = user_repo.get_ticker_follow(user.id, "AAPL")
    assert follow is not None
    assert follow.ticker == "AAPL"


def test_delete_ticker_follow(user_repo, sample_ticker):
    """Test deleting a ticker follow."""
    user_dto = UserCreateDTO(email="test@example.com")
    user = user_repo.create_user(user_dto)

    follow_dto = UserTickerFollowCreateDTO(user_id=user.id, ticker="AAPL")
    user_repo.create_ticker_follow(follow_dto)

    result = user_repo.delete_ticker_follow(user.id, "AAPL")
    assert result is True

    follow = user_repo.get_ticker_follow(user.id, "AAPL")
    assert follow is None


# Integration Tests


@pytest.mark.integration
def test_cascade_delete_user_removes_all_related(user_repo, sample_ticker):
    """Test that hard deleting a user cascades to all related records."""
    # Create user with profile, notification channels, and ticker follows
    user_dto = UserCreateDTO(email="test@example.com")
    user = user_repo.create_user(user_dto)

    # Create profile
    profile_dto = UserProfileCreateDTO(user_id=user.id, display_name="Test User")
    user_repo.create_profile(profile_dto)

    # Create notification channel
    channel_dto = UserNotificationChannelCreateDTO(
        user_id=user.id, channel_type="email", channel_value="test@example.com"
    )
    user_repo.create_notification_channel(channel_dto)

    # Create ticker follow
    follow_dto = UserTickerFollowCreateDTO(user_id=user.id, ticker="AAPL")
    user_repo.create_ticker_follow(follow_dto)

    # Hard delete user
    user_repo.hard_delete_user(user.id)

    # Verify all related records are gone
    assert user_repo.get_profile(user.id) is None
    assert len(user_repo.get_notification_channels(user.id)) == 0
    assert len(user_repo.get_ticker_follows(user.id)) == 0


@pytest.mark.integration
def test_complete_user_flow(user_repo, test_session):
    """Test a complete user creation flow with all related entities."""
    # Create tickers first
    aapl = Ticker(symbol="AAPL", name="Apple Inc.")
    tsla = Ticker(symbol="TSLA", name="Tesla Inc.")
    test_session.add_all([aapl, tsla])
    test_session.commit()

    # Create user
    user_dto = UserCreateDTO(
        email="alice@example.com",
        auth_provider="google",
        auth_provider_id="google_alice",
    )
    user = user_repo.create_user(user_dto)

    # Create profile
    profile_dto = UserProfileCreateDTO(
        user_id=user.id,
        display_name="Alice Johnson",
        timezone="America/New_York",
        bio="Tech investor",
    )
    profile = user_repo.create_profile(profile_dto)

    # Create notification channels
    email_channel = user_repo.create_notification_channel(
        UserNotificationChannelCreateDTO(
            user_id=user.id, channel_type="email", channel_value="alice@example.com"
        )
    )

    # Create ticker follows
    follow1 = user_repo.create_ticker_follow(
        UserTickerFollowCreateDTO(user_id=user.id, ticker="AAPL")
    )
    follow2 = user_repo.create_ticker_follow(
        UserTickerFollowCreateDTO(user_id=user.id, ticker="TSLA")
    )

    # Verify everything is created
    assert user.id is not None
    assert profile.user_id == user.id
    assert email_channel.user_id == user.id
    assert follow1.user_id == user.id
    assert follow2.user_id == user.id

    # Verify we can query everything
    retrieved_user = user_repo.get_user_by_id(user.id)
    assert retrieved_user is not None

    retrieved_profile = user_repo.get_profile(user.id)
    assert retrieved_profile is not None

    channels = user_repo.get_notification_channels(user.id)
    assert len(channels) == 1

    follows = user_repo.get_ticker_follows(user.id)
    assert len(follows) == 2


# Profile Update and Nickname Uniqueness Tests


def test_check_nickname_unique_available(user_repo):
    """Test nickname uniqueness check when available."""
    user_dto = UserCreateDTO(email="test@example.com")
    user = user_repo.create_user(user_dto)

    # Create profile with nickname
    profile_dto = UserProfileCreateDTO(
        user_id=user.id, display_name="ExistingNick", timezone="UTC"
    )
    user_repo.create_profile(profile_dto)

    # Check different nickname (should be available)
    assert user_repo.check_nickname_unique("NewNick") is True


def test_check_nickname_unique_taken(user_repo):
    """Test nickname uniqueness check when taken."""
    user_dto = UserCreateDTO(email="test@example.com")
    user = user_repo.create_user(user_dto)

    # Create profile with nickname
    profile_dto = UserProfileCreateDTO(
        user_id=user.id, display_name="ExistingNick", timezone="UTC"
    )
    user_repo.create_profile(profile_dto)

    # Check same nickname (should be taken)
    assert user_repo.check_nickname_unique("ExistingNick") is False


def test_check_nickname_unique_case_insensitive(user_repo):
    """Test nickname uniqueness is case-insensitive."""
    user_dto = UserCreateDTO(email="test@example.com")
    user = user_repo.create_user(user_dto)

    # Create profile with nickname
    profile_dto = UserProfileCreateDTO(
        user_id=user.id, display_name="ExistingNick", timezone="UTC"
    )
    user_repo.create_profile(profile_dto)

    # Check same nickname with different case (should be taken)
    assert user_repo.check_nickname_unique("existingnick") is False
    assert user_repo.check_nickname_unique("EXISTINGNICK") is False


def test_check_nickname_unique_exclude_user(user_repo):
    """Test nickname uniqueness check excludes specified user."""
    user1_dto = UserCreateDTO(email="user1@example.com")
    user1 = user_repo.create_user(user1_dto)

    # Create profile for user1
    profile_dto = UserProfileCreateDTO(
        user_id=user1.id, display_name="MyNick", timezone="UTC"
    )
    user_repo.create_profile(profile_dto)

    # User2 should be able to check same nickname (exclude user1)
    assert user_repo.check_nickname_unique("MyNick", exclude_user_id=user1.id) is True

    # But without exclude, it should be taken
    assert user_repo.check_nickname_unique("MyNick") is False


def test_update_profile_nickname(user_repo):
    """Test updating profile nickname."""
    user_dto = UserCreateDTO(email="test@example.com")
    user = user_repo.create_user(user_dto)

    # Create profile
    profile_dto = UserProfileCreateDTO(
        user_id=user.id, display_name="OldNick", timezone="UTC"
    )
    user_repo.create_profile(profile_dto)

    # Update nickname
    updated = user_repo.update_profile(user.id, nickname="NewNick")
    assert updated is not None
    assert updated.display_name == "NewNick"


def test_update_profile_nickname_uniqueness_violation(user_repo):
    """Test updating nickname fails if already taken."""
    user1_dto = UserCreateDTO(email="user1@example.com")
    user1 = user_repo.create_user(user1_dto)

    user2_dto = UserCreateDTO(email="user2@example.com")
    user2 = user_repo.create_user(user2_dto)

    # Create profiles with different nicknames
    user_repo.create_profile(
        UserProfileCreateDTO(user_id=user1.id, display_name="Nick1", timezone="UTC")
    )
    user_repo.create_profile(
        UserProfileCreateDTO(user_id=user2.id, display_name="Nick2", timezone="UTC")
    )

    # Try to update user2's nickname to user1's nickname
    with pytest.raises(ValueError, match="already taken"):
        user_repo.update_profile(user2.id, nickname="Nick1")


def test_update_profile_timezone(user_repo):
    """Test updating profile timezone."""
    user_dto = UserCreateDTO(email="test@example.com")
    user = user_repo.create_user(user_dto)

    profile_dto = UserProfileCreateDTO(user_id=user.id, timezone="UTC")
    user_repo.create_profile(profile_dto)

    # Update timezone
    updated = user_repo.update_profile(user.id, timezone="America/New_York")
    assert updated.timezone == "America/New_York"


def test_update_profile_notification_defaults(user_repo):
    """Test updating notification defaults."""
    user_dto = UserCreateDTO(email="test@example.com")
    user = user_repo.create_user(user_dto)

    profile_dto = UserProfileCreateDTO(user_id=user.id, timezone="UTC", preferences={})
    user_repo.create_profile(profile_dto)

    # Update notification defaults
    defaults = {"notify_on_surge": True, "email_enabled": False}
    updated = user_repo.update_profile(user.id, notification_defaults=defaults)
    assert updated.preferences is not None
    assert updated.preferences["notification_defaults"] == defaults


def test_update_profile_multiple_fields(user_repo):
    """Test updating multiple profile fields at once."""
    user_dto = UserCreateDTO(email="test@example.com")
    user = user_repo.create_user(user_dto)

    profile_dto = UserProfileCreateDTO(
        user_id=user.id,
        display_name="OldName",
        timezone="UTC",
    )
    user_repo.create_profile(profile_dto)

    # Update multiple fields
    updated = user_repo.update_profile(
        user.id,
        nickname="NewName",
        timezone="Europe/London",
        notification_defaults={
            "notify_on_surges": True,
            "notify_on_most_discussed": False,
        },
    )

    assert updated.display_name == "NewName"
    assert updated.timezone == "Europe/London"
    assert updated.preferences["notification_defaults"] == {
        "notify_on_surges": True,
        "notify_on_most_discussed": False,
    }


def test_update_profile_no_changes(user_repo):
    """Test updating profile with no changes."""
    user_dto = UserCreateDTO(email="test@example.com")
    user = user_repo.create_user(user_dto)

    profile_dto = UserProfileCreateDTO(user_id=user.id, timezone="UTC")
    original_profile = user_repo.create_profile(profile_dto)

    # Update with None values (no changes)
    updated = user_repo.update_profile(user.id)
    assert updated.display_name == original_profile.display_name
    assert updated.timezone == original_profile.timezone


def test_update_profile_not_found(user_repo):
    """Test updating profile when user doesn't exist."""
    result = user_repo.update_profile(999999, nickname="Test")
    assert result is None
