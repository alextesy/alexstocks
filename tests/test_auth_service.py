"""Unit tests for authentication service."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from jose import jwt

from app.config import settings
from app.db.models import User, UserProfile
from app.services.auth_service import (
    AuthService,
    BlockedAccountError,
    InvalidCredentialsError,
    MissingProfileDataError,
    NonGmailDomainError,
)


@pytest.fixture
def auth_service():
    """Create auth service instance."""
    return AuthService()


@pytest.fixture
def mock_db():
    """Create mock database session."""
    return MagicMock()


class TestAuthService:
    """Test cases for AuthService."""

    def test_get_google_oauth_url(self, auth_service):
        """Test generating Google OAuth URL."""
        state = "test_state_token"
        url = auth_service.get_google_oauth_url(state=state)

        assert "accounts.google.com/o/oauth2/v2/auth" in url
        assert f"client_id={settings.google_client_id}" in url
        assert f"redirect_uri={settings.google_redirect_uri}" in url
        assert "response_type=code" in url
        assert "scope=openid" in url and "email" in url and "profile" in url
        assert f"state={state}" in url

    def test_get_google_oauth_url_without_state(self, auth_service):
        """Test generating Google OAuth URL without state."""
        url = auth_service.get_google_oauth_url()

        assert "accounts.google.com/o/oauth2/v2/auth" in url
        assert "state=" not in url

    @pytest.mark.asyncio
    async def test_exchange_code_for_token_success(self, auth_service):
        """Test successful code exchange."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "access_token": "test_access_token",
            "refresh_token": "test_refresh_token",
        }
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                return_value=mock_response
            )

            result = await auth_service.exchange_code_for_token("test_code")

            assert result["access_token"] == "test_access_token"
            assert result["refresh_token"] == "test_refresh_token"

    @pytest.mark.asyncio
    async def test_exchange_code_for_token_failure(self, auth_service):
        """Test failed code exchange."""
        import httpx

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                side_effect=httpx.HTTPError("HTTP error")
            )

            with pytest.raises(InvalidCredentialsError):
                await auth_service.exchange_code_for_token("invalid_code")

    @pytest.mark.asyncio
    async def test_get_user_info_success(self, auth_service):
        """Test successful user info retrieval."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "id": "123456",
            "email": "test@gmail.com",
            "name": "Test User",
            "picture": "https://example.com/pic.jpg",
        }
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                return_value=mock_response
            )

            result = await auth_service.get_user_info("test_token")

            assert result["id"] == "123456"
            assert result["email"] == "test@gmail.com"
            assert result["name"] == "Test User"

    @pytest.mark.asyncio
    async def test_get_user_info_missing_data(self, auth_service):
        """Test user info with missing required fields."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "name": "Test User",
            # Missing email and id
        }
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                return_value=mock_response
            )

            with pytest.raises(MissingProfileDataError):
                await auth_service.get_user_info("test_token")

    def test_validate_gmail_domain_success(self, auth_service):
        """Test validating Gmail domain successfully."""
        # Should not raise exception
        auth_service.validate_gmail_domain("test@gmail.com")
        auth_service.validate_gmail_domain("Test.User@Gmail.Com")  # Case insensitive

    def test_validate_gmail_domain_failure(self, auth_service):
        """Test rejecting non-Gmail domains."""
        with pytest.raises(NonGmailDomainError):
            auth_service.validate_gmail_domain("test@yahoo.com")

        with pytest.raises(NonGmailDomainError):
            auth_service.validate_gmail_domain("test@outlook.com")

    @patch("app.services.auth_service.UserProfile")
    @patch("app.services.auth_service.User")
    def test_get_or_create_user_new_user(
        self, mock_user_class, mock_profile_class, auth_service, mock_db
    ):
        """Test creating a new user with profile."""
        # Mock query to return None (user doesn't exist)
        mock_query = MagicMock()
        mock_filter = MagicMock()
        mock_filter.first.return_value = None
        mock_query.filter.return_value = mock_filter
        mock_db.query.return_value = mock_query

        # Mock User constructor
        new_user = MagicMock()
        new_user.id = 1
        mock_user_class.return_value = new_user

        # Mock UserProfile constructor
        new_profile = MagicMock()
        mock_profile_class.return_value = new_profile

        result = auth_service.get_or_create_user(
            db=mock_db,
            auth_provider_id="123456",
            email="test@gmail.com",
            auth_provider="google",
            display_name="Test User",
            avatar_url="https://example.com/pic.jpg",
        )

        # Verify user was added to database
        assert mock_db.add.call_count >= 1  # User + Profile
        mock_db.commit.assert_called()
        assert result is not None

    @patch("app.services.auth_service.UserProfile")
    @patch("app.services.auth_service.User")
    def test_get_or_create_user_existing_user(
        self, mock_user_class, mock_profile_class, auth_service, mock_db
    ):
        """Test retrieving existing user updates profile."""
        # Create a proper mock with explicit False values
        existing_user = MagicMock()
        existing_user.id = 1
        existing_user.auth_provider_id = "123456"
        existing_user.email = "test@gmail.com"
        existing_user.is_active = True
        existing_user.is_deleted = False
        existing_user.__bool__ = lambda self: True  # Ensure user evaluates to True
        existing_user.created_at = datetime.now(UTC)
        existing_user.updated_at = datetime.now(UTC)

        # Configure the is_deleted check to work properly
        type(existing_user).is_deleted = property(lambda self: False)

        # Mock user query to return existing user
        mock_db.query.return_value.filter.return_value.first.return_value = (
            existing_user
        )

        # Mock profile query for UserProfile
        mock_profile_query = MagicMock()
        mock_profile_query.filter.return_value.first.return_value = None

        # Configure different returns based on what's queried
        original_query = mock_db.query

        def query_side_effect(model):
            if model is UserProfile:
                return mock_profile_query
            return original_query.return_value

        mock_db.query = MagicMock(side_effect=query_side_effect)

        result = auth_service.get_or_create_user(
            db=mock_db,
            auth_provider_id="123456",
            email="test@gmail.com",
            auth_provider="google",
            display_name="Updated Name",
        )

        # Verify commit was called
        mock_db.commit.assert_called()
        # Verify updated_at was set
        assert existing_user.updated_at is not None
        assert result is not None

    @patch("app.services.auth_service.User")
    def test_get_or_create_user_blocked_account(
        self, mock_user_class, auth_service, mock_db
    ):
        """Test blocked account cannot log in."""
        blocked_user = MagicMock()
        blocked_user.id = 1
        blocked_user.auth_provider_id = "123456"
        blocked_user.email = "test@gmail.com"
        blocked_user.is_active = False  # Account is blocked
        blocked_user.is_deleted = False
        blocked_user.created_at = datetime.now(UTC)
        blocked_user.updated_at = datetime.now(UTC)

        # Mock query to return blocked user
        mock_query = MagicMock()
        mock_filter = MagicMock()
        mock_filter.first.return_value = blocked_user
        mock_query.filter.return_value = mock_filter
        mock_db.query.return_value = mock_query

        with pytest.raises(BlockedAccountError):
            auth_service.get_or_create_user(
                db=mock_db,
                auth_provider_id="123456",
                email="test@gmail.com",
            )

    def test_create_session_token(self, auth_service):
        """Test creating JWT session token."""
        user_id = 123
        email = "test@gmail.com"

        token = auth_service.create_session_token(user_id, email)

        # Verify token can be decoded
        payload = jwt.decode(token, settings.session_secret_key, algorithms=["HS256"])
        assert payload["sub"] == str(user_id)
        assert payload["email"] == email
        assert "exp" in payload
        assert "iat" in payload

    def test_verify_session_token_success(self, auth_service):
        """Test verifying valid session token."""
        user_id = 123
        email = "test@gmail.com"

        token = auth_service.create_session_token(user_id, email)
        payload = auth_service.verify_session_token(token)

        assert payload["sub"] == str(user_id)
        assert payload["email"] == email

    def test_verify_session_token_invalid(self, auth_service):
        """Test verifying invalid token."""
        with pytest.raises(InvalidCredentialsError):
            auth_service.verify_session_token("invalid_token")

    def test_get_current_user_success(self, auth_service, mock_db):
        """Test getting current user from valid token."""
        user = MagicMock(spec=User)
        user.id = 123
        user.auth_provider_id = "123456"
        user.email = "test@gmail.com"
        user.is_active = True
        user.is_deleted = False
        user.created_at = datetime.now(UTC)
        user.updated_at = datetime.now(UTC)

        mock_db.query.return_value.filter.return_value.first.return_value = user

        token = auth_service.create_session_token(123, "test@gmail.com")
        result = auth_service.get_current_user(mock_db, token)

        assert result is not None
        assert result.id == 123
        assert result.email == "test@gmail.com"

    def test_get_current_user_invalid_token(self, auth_service, mock_db):
        """Test getting current user with invalid token."""
        result = auth_service.get_current_user(mock_db, "invalid_token")
        assert result is None

    def test_get_current_user_inactive_user(self, auth_service, mock_db):
        """Test getting current user returns None for inactive user."""
        mock_db.query.return_value.filter.return_value.first.return_value = None

        token = auth_service.create_session_token(123, "test@gmail.com")
        result = auth_service.get_current_user(mock_db, token)

        assert result is None
