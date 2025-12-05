"""Integration tests for user deletion API endpoint."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.models import Base
from app.db.session import get_db
from app.main import app
from app.models.dto import (
    UserCreateDTO,
    UserNotificationChannelCreateDTO,
    UserProfileCreateDTO,
    UserTickerFollowCreateDTO,
)
from app.repos.user_repo import UserRepository
from app.services.auth_service import AuthService


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
def override_db(test_session):
    """Override database dependency with test session."""

    def _get_db():
        yield test_session

    app.dependency_overrides[get_db] = _get_db
    yield
    app.dependency_overrides.clear()


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
    channel_dto = UserNotificationChannelCreateDTO(
        user_id=test_user.id,
        channel_type="email",
        channel_value="test@example.com",
        is_verified=True,
        is_enabled=True,
    )
    repo.create_notification_channel(channel_dto)

    # Create ticker follow
    follow_dto = UserTickerFollowCreateDTO(
        user_id=test_user.id,
        ticker="AAPL",
    )
    repo.create_ticker_follow(follow_dto)

    test_session.commit()
    return test_user


@pytest.fixture
def authenticated_client(test_user, override_db):
    """Create an authenticated test client."""
    auth_service = AuthService()
    session_token = auth_service.create_session_token(
        user_id=test_user.id, email=test_user.email
    )

    client = TestClient(app)
    client.cookies.set("session_token", session_token)
    return client


class TestUserDeletionAPI:
    """Test cases for DELETE /api/users/me endpoint."""

    def test_delete_user_authenticated(
        self, authenticated_client, test_user_with_related_data, test_session
    ):
        """Test authenticated user can delete their account."""
        user = test_user_with_related_data

        # Verify user exists before deletion
        repo = UserRepository(test_session)
        assert repo.get_user_by_id(user.id) is not None
        assert repo.get_profile(user.id) is not None

        # Delete account
        response = authenticated_client.delete("/api/users/me")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "message" in data
        assert len(data["message"]) > 0

        # Verify user is deleted
        assert repo.get_user_by_id(user.id, include_deleted=True) is None

        # Verify related data is deleted (CASCADE)
        assert repo.get_profile(user.id) is None
        assert len(repo.get_notification_channels(user.id)) == 0
        assert len(repo.get_ticker_follows(user.id)) == 0

    def test_delete_user_unauthenticated(self, override_db):
        """Test unauthenticated deletion request returns 401 and prevents deletion."""
        client = TestClient(app)
        response = client.delete("/api/users/me")

        assert response.status_code == 401
        assert "detail" in response.json()
        # Verify error message indicates authentication required
        detail = response.json()["detail"]
        assert (
            "authenticated" in detail.lower() or "not authenticated" in detail.lower()
        )

    def test_delete_user_removes_all_related_records(
        self, authenticated_client, test_user_with_related_data, test_session
    ):
        """Test that deletion removes all related records via CASCADE."""
        user = test_user_with_related_data

        # Verify related records exist
        repo = UserRepository(test_session)
        assert repo.get_profile(user.id) is not None
        assert len(repo.get_notification_channels(user.id)) > 0
        assert len(repo.get_ticker_follows(user.id)) > 0

        # Delete account
        response = authenticated_client.delete("/api/users/me")
        assert response.status_code == 200

        # Verify all related records are deleted
        assert repo.get_profile(user.id) is None
        assert len(repo.get_notification_channels(user.id)) == 0
        assert len(repo.get_ticker_follows(user.id)) == 0

    def test_delete_user_sessions_invalidated_after_deletion(
        self, authenticated_client, test_user_with_related_data, test_session
    ):
        """Test that sessions are invalidated after deletion."""
        # Delete account
        response = authenticated_client.delete("/api/users/me")
        assert response.status_code == 200

        # Try to use the same session token - should fail
        response = authenticated_client.get("/api/users/me")
        assert response.status_code == 401

    def test_delete_user_can_re_sign_in_after_deletion(
        self,
        authenticated_client,
        test_user_with_related_data,
        test_session,
        override_db,
    ):
        """Test that user can re-sign in after deletion and get a fresh account."""
        user = test_user_with_related_data
        original_email = user.email
        original_auth_provider_id = user.auth_provider_id
        original_user_id = user.id

        # Delete account
        response = authenticated_client.delete("/api/users/me")
        assert response.status_code == 200

        # Verify user is deleted
        repo = UserRepository(test_session)
        assert repo.get_user_by_id(original_user_id, include_deleted=True) is None

        # Create new user with same email/auth_provider_id (simulating re-sign in)
        new_user_dto = UserCreateDTO(
            email=original_email,
            auth_provider="google",
            auth_provider_id=original_auth_provider_id,
        )
        new_user = repo.create_user(new_user_dto)
        test_session.commit()

        # Verify new user was created with correct email
        assert new_user.email == original_email
        # Note: In SQLite, IDs may be reused after deletion, so we verify
        # the functional behavior (user deleted, new user created) rather than ID uniqueness

        # Verify new user can authenticate
        auth_service = AuthService()
        new_session_token = auth_service.create_session_token(
            user_id=new_user.id, email=new_user.email
        )

        new_client = TestClient(app)
        new_client.cookies.set("session_token", new_session_token)

        response = new_client.get("/api/users/me")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == new_user.id
        assert data["email"] == original_email

    def test_delete_user_confirmation_dialog_displays_data_list(
        self, authenticated_client, override_db
    ):
        """Test that confirmation dialog displays complete list of data to be deleted."""
        # Get settings page HTML to verify confirmation dialog content
        response = authenticated_client.get("/settings")
        assert response.status_code == 200

        html_content = response.text

        # Verify dialog exists
        assert "delete-account-dialog" in html_content

        # Verify warning about permanence
        assert (
            "cannot be undone" in html_content.lower()
            or "permanent" in html_content.lower()
        )

        # Verify list of data types to be deleted
        assert (
            "user profile" in html_content.lower() or "profile" in html_content.lower()
        )
        assert "watchlist" in html_content.lower() or "tickers" in html_content.lower()
        assert "notification" in html_content.lower()
        assert "email" in html_content.lower()
        assert (
            "weekly digest" in html_content.lower() or "digest" in html_content.lower()
        )

        # Verify cancel and confirm buttons exist
        assert "cancel-delete-button" in html_content
        assert "confirm-delete-button" in html_content
