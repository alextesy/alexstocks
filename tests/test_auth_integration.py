"""Integration tests for authentication flow."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app.db.models import Base, User, UserProfile
from app.main import app
from app.db.session import get_db


@pytest.fixture
def client(test_engine):
    """Create test client with database."""
    # Create all tables including User
    Base.metadata.create_all(bind=test_engine)

    TestingSessionLocal = sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=test_engine,
    )

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db

    test_client = TestClient(app)
    yield test_client

    app.dependency_overrides.pop(get_db, None)


@pytest.fixture
def mock_google_oauth():
    """Mock Google OAuth responses."""
    with (
        patch(
            "app.services.auth_service.AuthService.exchange_code_for_token"
        ) as mock_exchange,
        patch("app.services.auth_service.AuthService.get_user_info") as mock_user_info,
    ):

        # Mock successful token exchange
        mock_exchange.return_value = AsyncMock(
            return_value={
                "access_token": "test_access_token",
                "refresh_token": "test_refresh_token",
            }
        )

        # Mock successful user info retrieval
        mock_user_info.return_value = AsyncMock(
            return_value={
                "id": "google_123456",
                "email": "test@gmail.com",
                "name": "Test User",
                "picture": "https://example.com/pic.jpg",
            }
        )

        yield {
            "exchange": mock_exchange,
            "user_info": mock_user_info,
        }


class TestAuthIntegration:
    """Integration tests for authentication endpoints."""

    def test_login_page_renders(self, client):
        """Test login page renders successfully."""
        response = client.get("/auth/login")

        assert response.status_code == 200
        assert b"Sign in to AlexStocks" in response.content
        assert b"Sign in with Google" in response.content

    def test_login_page_with_error(self, client):
        """Test login page displays error messages."""
        response = client.get("/auth/login?error=non_gmail")

        assert response.status_code == 200
        assert b"Only Gmail accounts are supported" in response.content

    @pytest.mark.asyncio
    async def test_auth_callback_success_new_user(
        self, client, db_session, mock_google_oauth
    ):
        """Test successful OAuth callback creating new user."""
        # Mock the exchange and user info methods to be async
        with (
            patch(
                "app.services.auth_service.AuthService.exchange_code_for_token",
                new_callable=AsyncMock,
            ) as mock_exchange,
            patch(
                "app.services.auth_service.AuthService.get_user_info",
                new_callable=AsyncMock,
            ) as mock_user_info,
        ):

            mock_exchange.return_value = {
                "access_token": "test_access_token",
                "refresh_token": "test_refresh_token",
            }

            mock_user_info.return_value = {
                "id": "google_123456",
                "email": "test@gmail.com",
                "name": "Test User",
                "picture": "https://example.com/pic.jpg",
            }

            response = client.get(
                "/auth/callback",
                params={
                    "code": "test_auth_code",
                    "state": "test_state",
                },
                follow_redirects=False,
            )

            # Should redirect to home page
            assert response.status_code == 302
            assert response.headers["location"] == "/?login_event=true"

            # Should set session cookie
            assert "session_token" in response.cookies

            # Verify user was created in database
            user = db_session.query(User).filter(User.email == "test@gmail.com").first()
            assert user is not None
            assert user.auth_provider_id == "google_123456"
            assert user.auth_provider == "google"
            assert user.is_active is True
            assert user.is_deleted is False

            # Verify profile was created
            profile = (
                db_session.query(UserProfile)
                .filter(UserProfile.user_id == user.id)
                .first()
            )
            assert profile is not None
            assert profile.display_name == "Test User"
            assert profile.avatar_url == "https://example.com/pic.jpg"

    @pytest.mark.asyncio
    async def test_auth_callback_existing_user(self, client, db_session):
        """Test OAuth callback with existing user updates profile."""
        # Create existing user
        existing_user = User(
            auth_provider_id="google_123456",
            email="test@gmail.com",
            auth_provider="google",
            is_active=True,
            is_deleted=False,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        db_session.add(existing_user)
        db_session.flush()

        # Create existing profile
        existing_profile = UserProfile(
            user_id=existing_user.id,
            display_name="Old Name",
            timezone="UTC",
            avatar_url="https://example.com/old.jpg",
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        db_session.add(existing_profile)
        db_session.commit()

        old_updated_time = existing_user.updated_at

        with (
            patch(
                "app.services.auth_service.AuthService.exchange_code_for_token",
                new_callable=AsyncMock,
            ) as mock_exchange,
            patch(
                "app.services.auth_service.AuthService.get_user_info",
                new_callable=AsyncMock,
            ) as mock_user_info,
        ):

            mock_exchange.return_value = {
                "access_token": "test_access_token",
                "refresh_token": "test_refresh_token",
            }

            mock_user_info.return_value = {
                "id": "google_123456",
                "email": "test@gmail.com",
                "name": "Updated Name",
                "picture": "https://example.com/pic.jpg",
            }

            response = client.get(
                "/auth/callback",
                params={"code": "test_auth_code"},
                follow_redirects=False,
            )

            assert response.status_code == 302
            assert "session_token" in response.cookies

            # Verify user was updated
            db_session.refresh(existing_user)
            db_session.refresh(existing_profile)
            assert existing_profile.display_name == "Updated Name"
            assert existing_profile.avatar_url == "https://example.com/pic.jpg"
            assert existing_user.updated_at > old_updated_time

    @pytest.mark.asyncio
    async def test_auth_callback_non_gmail_rejected(self, client):
        """Test OAuth callback rejects non-Gmail accounts."""
        with (
            patch(
                "app.services.auth_service.AuthService.exchange_code_for_token",
                new_callable=AsyncMock,
            ) as mock_exchange,
            patch(
                "app.services.auth_service.AuthService.get_user_info",
                new_callable=AsyncMock,
            ) as mock_user_info,
        ):

            mock_exchange.return_value = {
                "access_token": "test_access_token",
            }

            mock_user_info.return_value = {
                "id": "google_123456",
                "email": "test@yahoo.com",  # Non-Gmail
                "name": "Test User",
            }

            response = client.get(
                "/auth/callback",
                params={"code": "test_auth_code"},
                follow_redirects=False,
            )

            # Should redirect to login with error
            assert response.status_code == 302
            assert "/auth/login?error=non_gmail" in response.headers["location"]

    @pytest.mark.asyncio
    async def test_auth_callback_blocked_account(self, client, db_session):
        """Test OAuth callback rejects blocked accounts."""
        # Create blocked user
        blocked_user = User(
            auth_provider_id="google_123456",
            email="blocked@gmail.com",
            auth_provider="google",
            is_active=False,  # Blocked
            is_deleted=False,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        db_session.add(blocked_user)
        db_session.commit()

        with (
            patch(
                "app.services.auth_service.AuthService.exchange_code_for_token",
                new_callable=AsyncMock,
            ) as mock_exchange,
            patch(
                "app.services.auth_service.AuthService.get_user_info",
                new_callable=AsyncMock,
            ) as mock_user_info,
        ):

            mock_exchange.return_value = {
                "access_token": "test_access_token",
            }

            mock_user_info.return_value = {
                "id": "google_123456",
                "email": "blocked@gmail.com",
                "name": "Blocked User",
            }

            response = client.get(
                "/auth/callback",
                params={"code": "test_auth_code"},
                follow_redirects=False,
            )

            # Should redirect to login with error
            assert response.status_code == 302
            assert "/auth/login?error=account_blocked" in response.headers["location"]

    def test_auth_callback_with_oauth_error(self, client):
        """Test OAuth callback handles OAuth errors."""
        response = client.get(
            "/auth/callback",
            params={"error": "access_denied"},
            follow_redirects=False,
        )

        assert response.status_code == 302
        assert "/auth/login?error=oauth_error" in response.headers["location"]

    def test_logout(self, client):
        """Test logout endpoint clears session."""
        response = client.get("/auth/logout", follow_redirects=False)

        assert response.status_code == 302
        assert response.headers["location"] == "/?logout_event=true"

        # Cookie should be deleted (set with empty value or expires in past)
        # FastAPI sets it to "" with max_age=0
        cookies = response.cookies
        assert "session_token" not in cookies or cookies["session_token"] == ""

    def test_get_current_user_authenticated(self, client, db_session):
        """Test /auth/me endpoint returns user info when authenticated."""
        from app.services.auth_service import AuthService

        # Create user
        user = User(
            auth_provider_id="google_123456",
            email="test@gmail.com",
            auth_provider="google",
            is_active=True,
            is_deleted=False,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        db_session.add(user)
        db_session.flush()

        # Create profile
        profile = UserProfile(
            user_id=user.id,
            display_name="Test User",
            timezone="UTC",
            avatar_url="https://example.com/pic.jpg",
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        db_session.add(profile)
        db_session.commit()

        # Create valid session token
        auth_service = AuthService()
        token = auth_service.create_session_token(user.id, user.email)

        response = client.get(
            "/auth/me",
            cookies={"session_token": token},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == user.id
        assert data["email"] == "test@gmail.com"
        assert data["name"] == "Test User"
        assert data["picture"] == "https://example.com/pic.jpg"

    def test_get_current_user_unauthenticated(self, client):
        """Test /auth/me endpoint returns 401 when not authenticated."""
        response = client.get("/auth/me")

        assert response.status_code == 401
        assert response.json()["detail"] == "Not authenticated"

    def test_get_current_user_invalid_token(self, client):
        """Test /auth/me endpoint returns 401 with invalid token."""
        response = client.get(
            "/auth/me",
            cookies={"session_token": "invalid_token"},
        )

        assert response.status_code == 401
        assert response.json()["detail"] == "Invalid session"
