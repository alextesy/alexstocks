"""Google OAuth authentication service."""

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from app.config import settings
from app.db.models import User

logger = logging.getLogger(__name__)


class AuthError(Exception):
    """Base exception for authentication errors."""

    pass


class InvalidCredentialsError(AuthError):
    """Raised when credentials are invalid."""

    pass


class BlockedAccountError(AuthError):
    """Raised when account is blocked or inactive."""

    pass


class MissingProfileDataError(AuthError):
    """Raised when required profile data is missing."""

    pass


class NonGmailDomainError(AuthError):
    """Raised when user attempts to sign in with non-Gmail account."""

    pass


class AuthService:
    """Service for Google OAuth authentication and user management."""

    GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
    GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v2/userinfo"

    def __init__(self) -> None:
        """Initialize auth service with configuration."""
        if not settings.google_client_id or not settings.google_client_secret:
            logger.warning(
                "google_oauth_config_missing",
                extra={
                    "has_client_id": bool(settings.google_client_id),
                    "has_client_secret": bool(settings.google_client_secret),
                },
            )

    def get_google_oauth_url(self, state: str | None = None) -> str:
        """Generate Google OAuth authorization URL.

        Args:
            state: Optional state parameter for CSRF protection

        Returns:
            Authorization URL for Google OAuth flow
        """
        params = {
            "client_id": settings.google_client_id,
            "redirect_uri": settings.google_redirect_uri,
            "response_type": "code",
            "scope": "openid email profile",
            "access_type": "offline",  # Request refresh token
            "prompt": "consent",  # Force consent screen to get refresh token
        }
        if state:
            params["state"] = state

        query_string = "&".join(f"{k}={v}" for k, v in params.items())
        return f"https://accounts.google.com/o/oauth2/v2/auth?{query_string}"

    async def exchange_code_for_token(self, code: str) -> dict[str, Any]:
        """Exchange authorization code for access token.

        Args:
            code: Authorization code from Google OAuth callback

        Returns:
            Token response containing access_token, id_token, etc.

        Raises:
            InvalidCredentialsError: If code exchange fails
        """
        token_data = {
            "code": code,
            "client_id": settings.google_client_id,
            "client_secret": settings.google_client_secret,
            "redirect_uri": settings.google_redirect_uri,
            "grant_type": "authorization_code",
        }

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    self.GOOGLE_TOKEN_URL,
                    data=token_data,
                    timeout=10.0,
                )
                response.raise_for_status()
                return response.json()
        except httpx.HTTPError as e:
            logger.error(
                "google_token_exchange_failed",
                extra={"error": str(e)},
            )
            raise InvalidCredentialsError("Failed to exchange authorization code") from e

    async def get_user_info(self, access_token: str) -> dict[str, Any]:
        """Fetch user profile information from Google.

        Args:
            access_token: Google OAuth access token

        Returns:
            User profile data from Google

        Raises:
            InvalidCredentialsError: If fetching user info fails
            MissingProfileDataError: If required profile data is missing
        """
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    self.GOOGLE_USERINFO_URL,
                    headers={"Authorization": f"Bearer {access_token}"},
                    timeout=10.0,
                )
                response.raise_for_status()
                user_info = response.json()

                # Validate required fields
                if not user_info.get("email") or not user_info.get("id"):
                    logger.error(
                        "google_userinfo_incomplete",
                        extra={"user_info": user_info},
                    )
                    raise MissingProfileDataError("Missing required profile data")

                return user_info
        except httpx.HTTPError as e:
            logger.error(
                "google_userinfo_fetch_failed",
                extra={"error": str(e)},
            )
            raise InvalidCredentialsError("Failed to fetch user information") from e

    def validate_gmail_domain(self, email: str) -> None:
        """Validate that email is from Gmail domain.

        Args:
            email: Email address to validate

        Raises:
            NonGmailDomainError: If email is not from Gmail domain
        """
        if not email.lower().endswith("@gmail.com"):
            logger.warning(
                "non_gmail_login_attempt",
                extra={"email_domain": email.split("@")[-1] if "@" in email else "unknown"},
            )
            raise NonGmailDomainError("Only Gmail accounts are currently supported")

    def get_or_create_user(
        self,
        db: Session,
        google_id: str,
        email: str,
        name: str | None = None,
        picture: str | None = None,
        refresh_token: str | None = None,
    ) -> User:
        """Get existing user or create new user record.

        Args:
            db: Database session
            google_id: Google user ID
            email: User email
            name: User full name
            picture: User profile picture URL
            refresh_token: OAuth refresh token (optional)

        Returns:
            User object (new or existing)

        Raises:
            BlockedAccountError: If user account is inactive
        """
        # Try to find existing user
        user = db.query(User).filter(User.google_id == google_id).first()

        if user:
            # Check if account is active
            if not user.is_active:
                logger.warning(
                    "blocked_account_login_attempt",
                    extra={"user_id": user.id, "email": user.email},
                )
                raise BlockedAccountError("Account is inactive")

            # Update last login and potentially refresh token
            user.last_login_at = datetime.now(UTC)
            if refresh_token:
                user.refresh_token = refresh_token
            if name:
                user.name = name
            if picture:
                user.picture = picture

            db.commit()
            db.refresh(user)

            logger.info(
                "user_logged_in",
                extra={"user_id": user.id, "email": user.email},
            )
        else:
            # Create new user
            user = User(
                google_id=google_id,
                email=email,
                name=name,
                picture=picture,
                refresh_token=refresh_token,
                is_active=True,
                created_at=datetime.now(UTC),
                last_login_at=datetime.now(UTC),
            )
            db.add(user)
            db.commit()
            db.refresh(user)

            logger.info(
                "user_created",
                extra={"user_id": user.id, "email": user.email},
            )

        return user

    def create_session_token(self, user_id: int, email: str) -> str:
        """Create JWT session token for authenticated user.

        Args:
            user_id: User ID
            email: User email

        Returns:
            Encoded JWT token
        """
        expire = datetime.now(UTC) + timedelta(seconds=settings.session_max_age_seconds)
        payload = {
            "sub": str(user_id),
            "email": email,
            "exp": expire,
            "iat": datetime.now(UTC),
        }

        token = jwt.encode(
            payload,
            settings.session_secret_key,
            algorithm="HS256",
        )

        logger.info(
            "session_token_created",
            extra={"user_id": user_id},
        )

        return token

    def verify_session_token(self, token: str) -> dict[str, Any]:
        """Verify and decode JWT session token.

        Args:
            token: JWT token to verify

        Returns:
            Token payload containing user info

        Raises:
            InvalidCredentialsError: If token is invalid or expired
        """
        try:
            payload = jwt.decode(
                token,
                settings.session_secret_key,
                algorithms=["HS256"],
            )
            return payload
        except JWTError as e:
            logger.warning(
                "invalid_session_token",
                extra={"error": str(e)},
            )
            raise InvalidCredentialsError("Invalid or expired session token") from e

    def get_current_user(self, db: Session, token: str) -> User | None:
        """Get current user from session token.

        Args:
            db: Database session
            token: JWT session token

        Returns:
            User object if token is valid, None otherwise
        """
        try:
            payload = self.verify_session_token(token)
            user_id = int(payload.get("sub", 0))
            if not user_id:
                return None

            user = db.query(User).filter(User.id == user_id, User.is_active == True).first()  # noqa: E712
            return user
        except (InvalidCredentialsError, ValueError):
            return None


def get_auth_service() -> AuthService:
    """Dependency to get auth service instance."""
    return AuthService()

