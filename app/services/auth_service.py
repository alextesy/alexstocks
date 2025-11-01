"""Google OAuth authentication service."""

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from jose import JWTError, jwt
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import settings
from app.db.models import User, UserProfile
from app.services.slack_service import get_slack_service

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
            raise InvalidCredentialsError(
                "Failed to exchange authorization code"
            ) from e

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
                extra={
                    "email_domain": email.split("@")[-1] if "@" in email else "unknown"
                },
            )
            raise NonGmailDomainError("Only Gmail accounts are currently supported")

    def get_or_create_user(
        self,
        db: Session,
        auth_provider_id: str,
        email: str,
        auth_provider: str = "google",
        display_name: str | None = None,
        avatar_url: str | None = None,
    ) -> User:
        """Get existing user or create new user record with profile.

        Args:
            db: Database session
            auth_provider_id: OAuth provider's user ID
            email: User email
            auth_provider: OAuth provider name (e.g., 'google')
            display_name: User display name (stored in profile)
            avatar_url: User avatar URL (stored in profile)

        Returns:
            User object (new or existing)

        Raises:
            BlockedAccountError: If user account is inactive or deleted
        """
        # Try to find existing user
        user = db.query(User).filter(User.auth_provider_id == auth_provider_id).first()

        if user:
            # Check if account is deleted
            if user.is_deleted:
                logger.warning(
                    "deleted_account_login_attempt",
                    extra={"user_id": user.id, "email": user.email},
                )
                raise BlockedAccountError("Account has been deleted")

            # Check if account is active
            if not user.is_active:
                logger.warning(
                    "blocked_account_login_attempt",
                    extra={"user_id": user.id, "email": user.email},
                )
                raise BlockedAccountError("Account is inactive")

            # Update last login time via updated_at
            user.updated_at = datetime.now(UTC)

            # Update or create profile if name/avatar provided
            if display_name or avatar_url:
                self._update_or_create_profile(db, user.id, display_name, avatar_url)

            db.commit()
            db.refresh(user)

            logger.info(
                "user_logged_in",
                extra={"user_id": user.id, "email": user.email},
            )
        else:
            # Create new user
            user = User(
                auth_provider_id=auth_provider_id,
                email=email,
                auth_provider=auth_provider,
                is_active=True,
                is_deleted=False,
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
            db.add(user)
            db.flush()  # Flush to get user.id

            # Create profile if name/avatar provided
            if display_name or avatar_url:
                self._create_profile(db, user.id, display_name, avatar_url)

            db.commit()
            db.refresh(user)

            logger.info(
                "user_created",
                extra={"user_id": user.id, "email": user.email},
            )

            # Send Slack notification for new user (non-blocking)
            try:
                total_users = (
                    db.query(func.count(User.id))
                    .filter(User.is_deleted == False)  # noqa: E712
                    .scalar()
                    or 0
                )

                profile = (
                    db.query(UserProfile).filter(UserProfile.user_id == user.id).first()
                )
                display_name = profile.display_name if profile else None

                slack = get_slack_service()
                slack.notify_user_created(
                    user_id=user.id,
                    email=user.email,
                    display_name=display_name,
                    total_users=total_users,
                )
            except Exception as e:
                # Don't fail login if Slack notification fails
                logger.warning(
                    "slack_user_notification_failed",
                    extra={"user_id": user.id, "error": str(e)},
                )

        return user

    def _generate_unique_display_name(
        self,
        db: Session,
        user_id: int,
        desired_name: str | None,
        current_name: str | None = None,
    ) -> str | None:
        """Generate a unique display name based on desired name.

        Args:
            db: Database session
            user_id: ID of user owning the profile
            desired_name: Preferred display name (may be None/empty)
            current_name: Existing display name (used to avoid unnecessary changes)

        Returns:
            Unique display name or None if no name provided
        """
        if not desired_name:
            return current_name

        base = desired_name.strip()
        if not base:
            return current_name

        # If unchanged (case-insensitive), keep current name
        if current_name and base.lower() == current_name.lower():
            return current_name

        max_length = 100
        base = base[:max_length]
        candidate = base
        counter = 2

        while (
            db.query(UserProfile)
            .filter(
                func.lower(UserProfile.display_name) == candidate.lower(),
                UserProfile.user_id != user_id,
            )
            .first()
        ):
            suffix = f"-{counter}"
            allowed_length = max_length - len(suffix)
            trimmed = base[:allowed_length] if allowed_length > 0 else ""
            if not trimmed:
                trimmed = (
                    f"user-{user_id}"[:allowed_length] if allowed_length > 0 else ""
                )
            candidate = f"{trimmed}{suffix}"
            counter += 1

        return candidate

    def _create_profile(
        self,
        db: Session,
        user_id: int,
        display_name: str | None = None,
        avatar_url: str | None = None,
    ) -> None:
        """Create user profile."""
        profile = UserProfile(
            user_id=user_id,
            display_name=self._generate_unique_display_name(
                db=db,
                user_id=user_id,
                desired_name=display_name,
            ),
            timezone="UTC",
            avatar_url=avatar_url,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        db.add(profile)
        db.flush()

    def _update_or_create_profile(
        self,
        db: Session,
        user_id: int,
        display_name: str | None = None,
        avatar_url: str | None = None,
    ) -> None:
        """Update existing profile or create if doesn't exist."""
        profile = db.query(UserProfile).filter(UserProfile.user_id == user_id).first()

        if profile:
            # Update existing profile
            if display_name:
                profile.display_name = self._generate_unique_display_name(
                    db=db,
                    user_id=user_id,
                    desired_name=display_name,
                    current_name=profile.display_name,
                )
            if avatar_url:
                profile.avatar_url = avatar_url
            profile.updated_at = datetime.now(UTC)
            db.flush()
        else:
            # Create new profile
            self._create_profile(db, user_id, display_name, avatar_url)

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

            user = (
                db.query(User)
                .filter(
                    User.id == user_id,
                    User.is_active == True,  # noqa: E712
                    User.is_deleted == False,  # noqa: E712
                )
                .first()
            )
            return user
        except (InvalidCredentialsError, ValueError):
            return None


def get_auth_service() -> AuthService:
    """Dependency to get auth service instance."""
    return AuthService()
