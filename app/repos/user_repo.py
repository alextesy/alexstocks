"""User repository for database operations."""

import logging
from datetime import UTC, datetime

from sqlalchemy import Text, cast, func, select
from sqlalchemy.orm import Session, joinedload

from app.config import settings
from app.db.models import (
    User,
    UserNotificationChannel,
    UserProfile,
    UserTickerFollow,
)
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

    def get_users_with_daily_briefing_enabled(self) -> list[UserDTO]:
        """Get all users with daily briefing notifications enabled.

        Returns:
            List of UserDTOs with daily briefing enabled
        """
        stmt = (
            select(User)
            .join(
                UserNotificationChannel,
                User.id == UserNotificationChannel.user_id,
            )
            .where(
                User.is_deleted == False,  # noqa: E712
                User.is_active == True,  # noqa: E712
                UserNotificationChannel.channel_type == "email",
                UserNotificationChannel.is_enabled == True,  # noqa: E712
                UserNotificationChannel.is_verified == True,  # noqa: E712
                cast(
                    UserNotificationChannel.preferences["notify_on_daily_briefing"],
                    Text,
                )
                == "true",
            )
        )
        users = self.session.execute(stmt).unique().scalars().all()
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

    def check_nickname_unique(
        self, nickname: str, exclude_user_id: int | None = None
    ) -> bool:
        """Check if nickname is unique (case-insensitive).

        Args:
            nickname: Nickname to check
            exclude_user_id: User ID to exclude from check (for updates)

        Returns:
            True if nickname is available, False if already taken
        """
        stmt = select(UserProfile).where(
            func.lower(UserProfile.display_name) == func.lower(nickname)
        )
        if exclude_user_id:
            stmt = stmt.where(UserProfile.user_id != exclude_user_id)

        existing = self.session.execute(stmt).scalar_one_or_none()
        return existing is None

    def update_profile(
        self,
        user_id: int,
        nickname: str | None = None,
        avatar_url: str | None = None,
        timezone: str | None = None,
        notification_defaults: dict | None = None,
    ) -> UserProfileDTO | None:
        """Update user profile with partial fields.

        Args:
            user_id: User ID to update
            nickname: New nickname (display_name), validated for uniqueness
            avatar_url: New avatar URL (optional, not exposed in UI for now)
            timezone: New timezone
            notification_defaults: Notification preferences (merged into profile.preferences)
                Expected keys: notify_on_surges, notify_on_most_discussed, notify_on_daily_briefing

        Returns:
            Updated profile DTO or None if user not found

        Raises:
            ValueError: If nickname is already taken
        """
        profile = self.session.get(UserProfile, user_id)
        if not profile:
            return None

        updated = False

        if nickname is not None:
            # Check uniqueness (case-insensitive)
            if not self.check_nickname_unique(nickname, exclude_user_id=user_id):
                raise ValueError(f"Nickname '{nickname}' is already taken")

            profile.display_name = nickname
            updated = True

        if avatar_url is not None:
            profile.avatar_url = avatar_url
            updated = True

        if timezone is not None:
            profile.timezone = timezone
            updated = True

        if notification_defaults is not None:
            # Merge notification defaults into preferences
            if profile.preferences is None:
                profile.preferences = {}
            profile.preferences["notification_defaults"] = notification_defaults
            updated = True

        if updated:
            profile.updated_at = datetime.now(UTC)
            self.session.flush()

        return self._profile_to_dto(profile)

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

    def get_notification_channels(
        self, user_id: int
    ) -> list[UserNotificationChannelDTO]:
        """Get all notification channels for a user."""
        stmt = (
            select(UserNotificationChannel)
            .where(UserNotificationChannel.user_id == user_id)
            .order_by(UserNotificationChannel.created_at)
        )
        channels = self.session.execute(stmt).scalars().all()
        return [self._notification_channel_to_dto(ch) for ch in channels]

    def update_notification_channel(
        self,
        channel_id: int,
        is_enabled: bool | None = None,
        is_verified: bool | None = None,
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

    def find_channel_by_email(self, email: str) -> UserNotificationChannelDTO | None:
        """Find notification channel by email address.

        Args:
            email: Email address to search for

        Returns:
            UserNotificationChannelDTO if found, None otherwise
        """
        stmt = select(UserNotificationChannel).where(
            UserNotificationChannel.channel_type == "email",
            UserNotificationChannel.channel_value == email.lower(),
        )
        channel = self.session.execute(stmt).scalar_one_or_none()
        return self._notification_channel_to_dto(channel) if channel else None

    def mark_email_bounced(
        self,
        email: str,
        bounce_type: str,
        disable_channel: bool = False,
    ) -> UserNotificationChannelDTO | None:
        """Mark an email notification channel as bounced.

        Args:
            email: Email address that bounced
            bounce_type: Type of bounce ('Permanent', 'Transient', etc.)
            disable_channel: If True, also disable the channel (for permanent bounces)

        Returns:
            Updated UserNotificationChannelDTO if found, None otherwise
        """
        stmt = select(UserNotificationChannel).where(
            UserNotificationChannel.channel_type == "email",
            UserNotificationChannel.channel_value == email.lower(),
        )
        channel = self.session.execute(stmt).scalar_one_or_none()
        if not channel:
            return None

        channel.email_bounced = True
        channel.bounced_at = datetime.now(UTC)
        channel.bounce_type = bounce_type
        if disable_channel:
            channel.is_enabled = False
        channel.updated_at = datetime.now(UTC)
        self.session.flush()
        return self._notification_channel_to_dto(channel)

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

        # Get max order for this user to append at end
        max_order_stmt = select(func.max(UserTickerFollow.order)).where(
            UserTickerFollow.user_id == follow_dto.user_id
        )
        max_order_result = self.session.execute(max_order_stmt).scalar()
        next_order = (max_order_result if max_order_result is not None else -1) + 1

        # Create new follow
        follow = UserTickerFollow(
            user_id=follow_dto.user_id,
            ticker=follow_dto.ticker,
            notify_on_signals=follow_dto.notify_on_signals,
            notify_on_price_change=follow_dto.notify_on_price_change,
            price_change_threshold=follow_dto.price_change_threshold,
            custom_alerts=follow_dto.custom_alerts,
            order=next_order,
        )
        self.session.add(follow)
        self.session.flush()
        return self._ticker_follow_to_dto(follow)

    def get_ticker_follows(
        self, user_id: int, limit: int = 100, offset: int = 0
    ) -> list[UserTickerFollowDTO]:
        """Get all ticker follows for a user with pagination, ordered by order field."""
        max_limit = getattr(settings, "MAX_LIMIT_TICKERS", 100)
        limit = min(limit, max_limit)

        stmt = (
            select(UserTickerFollow)
            .options(joinedload(UserTickerFollow.ticker_obj))
            .where(UserTickerFollow.user_id == user_id)
            .order_by(UserTickerFollow.order.asc(), UserTickerFollow.created_at.asc())
            .limit(limit)
            .offset(offset)
        )
        follows = self.session.execute(stmt).unique().scalars().all()
        return [self._ticker_follow_to_dto(f) for f in follows]

    def get_ticker_follow(
        self, user_id: int, ticker: str
    ) -> UserTickerFollowDTO | None:
        """Get a specific ticker follow."""
        stmt = select(UserTickerFollow).where(
            UserTickerFollow.user_id == user_id, UserTickerFollow.ticker == ticker
        )
        follow = self.session.execute(stmt).scalar_one_or_none()
        return self._ticker_follow_to_dto(follow) if follow else None

    def delete_ticker_follow(self, user_id: int, ticker: str) -> bool:
        """Delete a ticker follow and reorder remaining follows."""
        stmt = select(UserTickerFollow).where(
            UserTickerFollow.user_id == user_id, UserTickerFollow.ticker == ticker
        )
        follow = self.session.execute(stmt).scalar_one_or_none()
        if not follow:
            return False

        deleted_order = follow.order

        self.session.delete(follow)
        self.session.flush()

        # Reorder remaining follows: shift down orders > deleted_order
        reorder_stmt = (
            select(UserTickerFollow)
            .where(
                UserTickerFollow.user_id == user_id,
                UserTickerFollow.order > deleted_order,
            )
            .order_by(UserTickerFollow.order.asc())
        )
        remaining_follows = self.session.execute(reorder_stmt).scalars().all()
        for remaining in remaining_follows:
            remaining.order -= 1
            remaining.updated_at = datetime.now(UTC)
        self.session.flush()

        return True

    def reorder_ticker_follows(
        self, user_id: int, ticker_orders: dict[str, int]
    ) -> list[UserTickerFollowDTO]:
        """Reorder ticker follows for a user.

        Args:
            user_id: User ID
            ticker_orders: Dictionary mapping ticker symbols to their new order positions

        Returns:
            List of updated ticker follow DTOs in new order
        """
        # Get all follows for this user
        stmt = select(UserTickerFollow).where(
            UserTickerFollow.user_id == user_id,
            UserTickerFollow.ticker.in_(list(ticker_orders.keys())),
        )
        follows = self.session.execute(stmt).scalars().all()

        # Update orders
        for follow in follows:
            if follow.ticker in ticker_orders:
                follow.order = ticker_orders[follow.ticker]
                follow.updated_at = datetime.now(UTC)

        self.session.flush()

        # Return all follows in order
        return self.get_ticker_follows(user_id)

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
            email_bounced=channel.email_bounced,
            bounced_at=channel.bounced_at,
            bounce_type=channel.bounce_type,
            created_at=channel.created_at,
            updated_at=channel.updated_at,
        )

    @staticmethod
    def _ticker_follow_to_dto(follow: UserTickerFollow) -> UserTickerFollowDTO:
        """Convert UserTickerFollow model to DTO."""
        # Get ticker name if relationship is loaded
        ticker_name = None
        if follow.ticker_obj:
            ticker_name = follow.ticker_obj.name
        elif hasattr(follow, "ticker_obj") and follow.ticker_obj is not None:
            ticker_name = follow.ticker_obj.name

        return UserTickerFollowDTO(
            id=follow.id,
            user_id=follow.user_id,
            ticker=follow.ticker,
            ticker_name=ticker_name,
            order=follow.order,
            notify_on_signals=follow.notify_on_signals,
            notify_on_price_change=follow.notify_on_price_change,
            price_change_threshold=follow.price_change_threshold,
            custom_alerts=follow.custom_alerts,
            created_at=follow.created_at,
            updated_at=follow.updated_at,
        )
