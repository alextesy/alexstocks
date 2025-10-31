"""User repository for database operations."""

import logging
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.config import settings
from app.db.models import User, UserNotificationChannel, UserProfile, UserTickerFollow
from app.models.dto import (
    UserCreateDTO,
    UserDTO,
    UserNotificationChannelCreateDTO,
    UserNotificationChannelDTO,
    UserProfileCreateDTO,
    UserProfileDTO,
    UserTickerFollowCreateDTO,
    UserTickerFollowDTO,
)

logger = logging.getLogger(__name__)


class UserRepository:
    """Repository for user CRUD operations with soft-delete support."""

    def __init__(self, session: Session):
        """Initialize repository with database session."""
        self.session = session

    def create_user(self, user_dto: UserCreateDTO) -> UserDTO:
        """Create a new user."""
        user = User(
            email=user_dto.email,
            auth_provider_id=user_dto.auth_provider_id,
            auth_provider=user_dto.auth_provider,
        )
        self.session.add(user)
        self.session.flush()
        return self._user_to_dto(user)

    def get_user_by_id(
        self, user_id: int, include_deleted: bool = False
    ) -> UserDTO | None:
        """Get user by ID."""
        stmt = select(User).where(User.id == user_id)
        if not include_deleted:
            stmt = stmt.where(User.is_deleted == False)  # noqa: E712

        user = self.session.execute(stmt).scalar_one_or_none()
        return self._user_to_dto(user) if user else None

    def get_user_by_email(
        self, email: str, include_deleted: bool = False
    ) -> UserDTO | None:
        """Get user by email."""
        stmt = select(User).where(User.email == email)
        if not include_deleted:
            stmt = stmt.where(User.is_deleted == False)  # noqa: E712

        user = self.session.execute(stmt).scalar_one_or_none()
        return self._user_to_dto(user) if user else None

    def get_user_by_auth_provider_id(
        self, auth_provider_id: str, include_deleted: bool = False
    ) -> UserDTO | None:
        """Get user by OAuth provider ID."""
        stmt = select(User).where(User.auth_provider_id == auth_provider_id)
        if not include_deleted:
            stmt = stmt.where(User.is_deleted == False)  # noqa: E712

        user = self.session.execute(stmt).scalar_one_or_none()
        return self._user_to_dto(user) if user else None

    def list_users(
        self,
        limit: int = 100,
        offset: int = 0,
        include_deleted: bool = False,
    ) -> list[UserDTO]:
        """List users with pagination."""
        stmt = select(User)
        if not include_deleted:
            stmt = stmt.where(User.is_deleted == False)  # noqa: E712

        stmt = stmt.order_by(User.created_at.desc()).limit(limit).offset(offset)
        users = self.session.execute(stmt).scalars().all()
        return [self._user_to_dto(user) for user in users]

    def update_user(
        self, user_id: int, is_active: bool | None = None
    ) -> UserDTO | None:
        """Update user fields."""
        user = self.session.get(User, user_id)
        if not user or user.is_deleted:
            return None

        if is_active is not None:
            user.is_active = is_active

        user.updated_at = datetime.now(UTC)
        self.session.flush()
        return self._user_to_dto(user)

    def soft_delete_user(self, user_id: int) -> bool:
        """Soft delete a user."""
        user = self.session.get(User, user_id)
        if not user or user.is_deleted:
            return False

        user.is_deleted = True
        user.is_active = False
        user.deleted_at = datetime.now(UTC)
        user.updated_at = datetime.now(UTC)
        self.session.flush()
        return True

    def restore_user(self, user_id: int) -> bool:
        """Restore a soft-deleted user."""
        user = self.session.get(User, user_id)
        if not user or not user.is_deleted:
            return False

        user.is_deleted = False
        user.is_active = True
        user.deleted_at = None
        user.updated_at = datetime.now(UTC)
        self.session.flush()
        return True

    def hard_delete_user(self, user_id: int) -> bool:
        """Permanently delete a user (cascade to related records)."""
        user = self.session.get(User, user_id)
        if not user:
            return False

        self.session.delete(user)
        self.session.flush()
        return True

    # UserProfile operations
    def create_profile(self, profile_dto: UserProfileCreateDTO) -> UserProfileDTO:
        """Create or update user profile."""
        # Check if profile exists
        existing = self.session.get(UserProfile, profile_dto.user_id)
        if existing:
            # Update existing profile
            existing.display_name = profile_dto.display_name
            existing.timezone = profile_dto.timezone
            existing.avatar_url = profile_dto.avatar_url
            existing.bio = profile_dto.bio
            existing.preferences = profile_dto.preferences
            existing.updated_at = datetime.now(UTC)
            self.session.flush()
            return self._profile_to_dto(existing)

        # Create new profile
        profile = UserProfile(
            user_id=profile_dto.user_id,
            display_name=profile_dto.display_name,
            timezone=profile_dto.timezone,
            avatar_url=profile_dto.avatar_url,
            bio=profile_dto.bio,
            preferences=profile_dto.preferences,
        )
        self.session.add(profile)
        self.session.flush()
        return self._profile_to_dto(profile)

    def get_profile(self, user_id: int) -> UserProfileDTO | None:
        """Get user profile."""
        profile = self.session.get(UserProfile, user_id)
        return self._profile_to_dto(profile) if profile else None

    # UserNotificationChannel operations
    def create_notification_channel(
        self, channel_dto: UserNotificationChannelCreateDTO
    ) -> UserNotificationChannelDTO:
        """Create a notification channel."""
        channel = UserNotificationChannel(
            user_id=channel_dto.user_id,
            channel_type=channel_dto.channel_type,
            channel_value=channel_dto.channel_value,
            is_verified=channel_dto.is_verified,
            is_enabled=channel_dto.is_enabled,
            preferences=channel_dto.preferences,
        )
        self.session.add(channel)
        self.session.flush()
        return self._notification_channel_to_dto(channel)

    def get_notification_channels(self, user_id: int) -> list[UserNotificationChannelDTO]:
        """Get all notification channels for a user."""
        stmt = (
            select(UserNotificationChannel)
            .where(UserNotificationChannel.user_id == user_id)
            .order_by(UserNotificationChannel.created_at)
        )
        channels = self.session.execute(stmt).scalars().all()
        return [self._notification_channel_to_dto(ch) for ch in channels]

    def update_notification_channel(
        self, channel_id: int, is_enabled: bool | None = None, is_verified: bool | None = None
    ) -> UserNotificationChannelDTO | None:
        """Update notification channel."""
        channel = self.session.get(UserNotificationChannel, channel_id)
        if not channel:
            return None

        if is_enabled is not None:
            channel.is_enabled = is_enabled
        if is_verified is not None:
            channel.is_verified = is_verified

        channel.updated_at = datetime.now(UTC)
        self.session.flush()
        return self._notification_channel_to_dto(channel)

    def delete_notification_channel(self, channel_id: int) -> bool:
        """Delete a notification channel."""
        channel = self.session.get(UserNotificationChannel, channel_id)
        if not channel:
            return False

        self.session.delete(channel)
        self.session.flush()
        return True

    # UserTickerFollow operations
    def create_ticker_follow(
        self, follow_dto: UserTickerFollowCreateDTO
    ) -> UserTickerFollowDTO:
        """Create a ticker follow (with duplicate check)."""
        # Check for existing follow
        stmt = select(UserTickerFollow).where(
            UserTickerFollow.user_id == follow_dto.user_id,
            UserTickerFollow.ticker == follow_dto.ticker,
        )
        existing = self.session.execute(stmt).scalar_one_or_none()
        if existing:
            # Update existing follow
            existing.notify_on_signals = follow_dto.notify_on_signals
            existing.notify_on_price_change = follow_dto.notify_on_price_change
            existing.price_change_threshold = follow_dto.price_change_threshold
            existing.custom_alerts = follow_dto.custom_alerts
            existing.updated_at = datetime.now(UTC)
            self.session.flush()
            return self._ticker_follow_to_dto(existing)

        # Create new follow
        follow = UserTickerFollow(
            user_id=follow_dto.user_id,
            ticker=follow_dto.ticker,
            notify_on_signals=follow_dto.notify_on_signals,
            notify_on_price_change=follow_dto.notify_on_price_change,
            price_change_threshold=follow_dto.price_change_threshold,
            custom_alerts=follow_dto.custom_alerts,
        )
        self.session.add(follow)
        self.session.flush()
        return self._ticker_follow_to_dto(follow)

    def get_ticker_follows(
        self, user_id: int, limit: int = 100, offset: int = 0
    ) -> list[UserTickerFollowDTO]:
        """Get all ticker follows for a user with pagination."""
        max_limit = getattr(settings, "MAX_LIMIT_TICKERS", 100)
        limit = min(limit, max_limit)

        stmt = (
            select(UserTickerFollow)
            .where(UserTickerFollow.user_id == user_id)
            .order_by(UserTickerFollow.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        follows = self.session.execute(stmt).scalars().all()
        return [self._ticker_follow_to_dto(f) for f in follows]

    def get_ticker_follow(self, user_id: int, ticker: str) -> UserTickerFollowDTO | None:
        """Get a specific ticker follow."""
        stmt = select(UserTickerFollow).where(
            UserTickerFollow.user_id == user_id, UserTickerFollow.ticker == ticker
        )
        follow = self.session.execute(stmt).scalar_one_or_none()
        return self._ticker_follow_to_dto(follow) if follow else None

    def delete_ticker_follow(self, user_id: int, ticker: str) -> bool:
        """Delete a ticker follow."""
        stmt = select(UserTickerFollow).where(
            UserTickerFollow.user_id == user_id, UserTickerFollow.ticker == ticker
        )
        follow = self.session.execute(stmt).scalar_one_or_none()
        if not follow:
            return False

        self.session.delete(follow)
        self.session.flush()
        return True

    # Helper methods to convert models to DTOs
    @staticmethod
    def _user_to_dto(user: User) -> UserDTO:
        """Convert User model to UserDTO."""
        return UserDTO(
            id=user.id,
            email=user.email,
            auth_provider_id=user.auth_provider_id,
            auth_provider=user.auth_provider,
            is_active=user.is_active,
            is_deleted=user.is_deleted,
            created_at=user.created_at,
            updated_at=user.updated_at,
            deleted_at=user.deleted_at,
        )

    @staticmethod
    def _profile_to_dto(profile: UserProfile) -> UserProfileDTO:
        """Convert UserProfile model to UserProfileDTO."""
        return UserProfileDTO(
            user_id=profile.user_id,
            display_name=profile.display_name,
            timezone=profile.timezone,
            avatar_url=profile.avatar_url,
            bio=profile.bio,
            preferences=profile.preferences,
            created_at=profile.created_at,
            updated_at=profile.updated_at,
        )

    @staticmethod
    def _notification_channel_to_dto(
        channel: UserNotificationChannel,
    ) -> UserNotificationChannelDTO:
        """Convert UserNotificationChannel model to DTO."""
        return UserNotificationChannelDTO(
            id=channel.id,
            user_id=channel.user_id,
            channel_type=channel.channel_type,
            channel_value=channel.channel_value,
            is_verified=channel.is_verified,
            is_enabled=channel.is_enabled,
            preferences=channel.preferences,
            created_at=channel.created_at,
            updated_at=channel.updated_at,
        )

    @staticmethod
    def _ticker_follow_to_dto(follow: UserTickerFollow) -> UserTickerFollowDTO:
        """Convert UserTickerFollow model to DTO."""
        return UserTickerFollowDTO(
            id=follow.id,
            user_id=follow.user_id,
            ticker=follow.ticker,
            notify_on_signals=follow.notify_on_signals,
            notify_on_price_change=follow.notify_on_price_change,
            price_change_threshold=follow.price_change_threshold,
            custom_alerts=follow.custom_alerts,
            created_at=follow.created_at,
            updated_at=follow.updated_at,
        )

