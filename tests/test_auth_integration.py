"""Integration tests for authentication flow."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.db.models import Base, User
from app.main import app


@pytest.fixture
def client(test_engine):
    """Create test client with database."""
    # Create all tables including User
    Base.metadata.create_all(bind=test_engine)

    return TestClient(app)


@pytest.fixture
def mock_google_oauth():
    """Mock Google OAuth responses."""
    with patch("app.services.auth_service.AuthService.exchange_code_for_token") as mock_exchange, \
         patch("app.services.auth_service.AuthService.get_user_info") as mock_user_info:

        # Mock successful token exchange
        mock_exchange.return_value = AsyncMock(return_value={
            "access_token": "test_access_token",
            "refresh_token": "test_refresh_token",
        })

        # Mock successful user info retrieval
        mock_user_info.return_value = AsyncMock(return_value={
            "id": "google_123456",
            "email": "test@gmail.com",
            "name": "Test User",
            "picture": "https://example.com/pic.jpg",
        })

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
    async def test_auth_callback_success_new_user(self, client, db_session, mock_google_oauth):
        """Test successful OAuth callback creating new user."""
        # Mock the exchange and user info methods to be async
        with patch("app.services.auth_service.AuthService.exchange_code_for_token", new_callable=AsyncMock) as mock_exchange, \
             patch("app.services.auth_service.AuthService.get_user_info", new_callable=AsyncMock) as mock_user_info:

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
            assert response.headers["location"] == "/"

            # Should set session cookie
            assert "session_token" in response.cookies

            # Verify user was created in database
            user = db_session.query(User).filter(User.email == "test@gmail.com").first()
            assert user is not None
            assert user.google_id == "google_123456"
            assert user.name == "Test User"
            assert user.is_active is True

    @pytest.mark.asyncio
    async def test_auth_callback_existing_user(self, client, db_session):
        """Test OAuth callback with existing user updates login time."""
        # Create existing user
        existing_user = User(
            google_id="google_123456",
            email="test@gmail.com",
            name="Old Name",
            is_active=True,
            created_at=datetime.now(UTC),
            last_login_at=datetime.now(UTC),
        )
        db_session.add(existing_user)
        db_session.commit()
        old_login_time = existing_user.last_login_at

        with patch("app.services.auth_service.AuthService.exchange_code_for_token", new_callable=AsyncMock) as mock_exchange, \
             patch("app.services.auth_service.AuthService.get_user_info", new_callable=AsyncMock) as mock_user_info:

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
            assert existing_user.name == "Updated Name"
            assert existing_user.last_login_at > old_login_time

    @pytest.mark.asyncio
    async def test_auth_callback_non_gmail_rejected(self, client):
        """Test OAuth callback rejects non-Gmail accounts."""
        with patch("app.services.auth_service.AuthService.exchange_code_for_token", new_callable=AsyncMock) as mock_exchange, \
             patch("app.services.auth_service.AuthService.get_user_info", new_callable=AsyncMock) as mock_user_info:

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
            google_id="google_123456",
            email="blocked@gmail.com",
            name="Blocked User",
            is_active=False,  # Blocked
            created_at=datetime.now(UTC),
            last_login_at=datetime.now(UTC),
        )
        db_session.add(blocked_user)
        db_session.commit()

        with patch("app.services.auth_service.AuthService.exchange_code_for_token", new_callable=AsyncMock) as mock_exchange, \
             patch("app.services.auth_service.AuthService.get_user_info", new_callable=AsyncMock) as mock_user_info:

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
        assert response.headers["location"] == "/"

        # Cookie should be deleted (set with empty value or expires in past)
        # FastAPI sets it to "" with max_age=0
        cookies = response.cookies
        assert "session_token" not in cookies or cookies["session_token"] == ""

    def test_get_current_user_authenticated(self, client, db_session):
        """Test /auth/me endpoint returns user info when authenticated."""
        from app.services.auth_service import AuthService

        # Create user
        user = User(
            id=1,
            google_id="google_123456",
            email="test@gmail.com",
            name="Test User",
            picture="https://example.com/pic.jpg",
            is_active=True,
            created_at=datetime.now(UTC),
            last_login_at=datetime.now(UTC),
        )
        db_session.add(user)
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
        assert data["id"] == 1
        assert data["email"] == "test@gmail.com"
        assert data["name"] == "Test User"

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

