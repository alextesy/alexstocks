"""Helpers for managing user notification channels."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import UserNotificationChannel, UserProfile


def ensure_email_notification_channel(
    db: Session,
    user_id: int,
    email: str,
    preferences: dict | None = None,
) -> tuple[UserNotificationChannel, bool, bool]:
    """Ensure an email notification channel exists for the user.

    Args:
        db: Active database session.
        user_id: ID of the user the channel belongs to.
        email: Email address to store as the channel value.
        preferences: Optional channel-specific preferences to persist.
            If provided, will be merged with defaults (notify_on_daily_briefing=True).

    Returns:
        Tuple of (channel, created_flag, updated_flag).
    """
    stmt = select(UserNotificationChannel).where(
        UserNotificationChannel.user_id == user_id,
        UserNotificationChannel.channel_type == "email",
    )
    channel = db.execute(stmt).scalar_one_or_none()
    now = datetime.now(UTC)

    # Default preferences - notify_on_daily_briefing defaults to True
    default_preferences = {"notify_on_daily_briefing": True}

    if channel:
        updated = False
        if channel.channel_value != email:
            channel.channel_value = email
            updated = True
        if not channel.is_enabled:
            channel.is_enabled = True
            updated = True
        if not channel.is_verified:
            channel.is_verified = True
            updated = True

        # Handle preferences merging
        if preferences is not None:
            # New preferences provided - merge with defaults (preferences override defaults)
            merged_preferences = {**default_preferences, **preferences}
            if channel.preferences != merged_preferences:
                channel.preferences = merged_preferences
                updated = True
        else:
            # No new preferences provided - ensure defaults are set
            if channel.preferences is None:
                channel.preferences = default_preferences
                updated = True
            elif "notify_on_daily_briefing" not in channel.preferences:
                # Add default if missing
                channel.preferences = {**default_preferences, **channel.preferences}
                updated = True

        if updated:
            channel.updated_at = now
            db.flush()

        # Always sync preferences back to user_profile.notification_defaults
        # This ensures alignment even if channel wasn't updated
        _sync_preferences_to_profile(db, user_id, channel.preferences)

        return channel, False, updated

    # For new channels, merge provided preferences with defaults
    if preferences is not None:
        final_preferences = {**default_preferences, **preferences}
    else:
        final_preferences = default_preferences

    channel = UserNotificationChannel(
        user_id=user_id,
        channel_type="email",
        channel_value=email,
        is_verified=True,
        is_enabled=True,
        preferences=final_preferences,
        created_at=now,
        updated_at=now,
    )
    db.add(channel)
    db.flush()

    # Sync preferences back to user_profile.notification_defaults
    _sync_preferences_to_profile(db, user_id, final_preferences)

    return channel, True, True


def _sync_preferences_to_profile(
    db: Session, user_id: int, channel_preferences: dict | None
) -> None:
    """Sync notification channel preferences to user_profile.notification_defaults.

    Creates profile if it doesn't exist, then syncs preferences.

    Args:
        db: Active database session.
        user_id: ID of the user.
        channel_preferences: Preferences from notification channel.
    """
    # Use merge to ensure we get the object from the current session
    # This avoids issues with stale objects
    profile = db.get(UserProfile, user_id)

    # Create profile if it doesn't exist
    if not profile:
        profile = UserProfile(
            user_id=user_id,
            timezone="UTC",
            preferences={},
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        db.add(profile)
        db.flush()

    # Extract notification_defaults from channel preferences
    # Channel preferences are stored directly, profile stores them under notification_defaults key
    if channel_preferences is None:
        channel_preferences = {}

    # Update profile preferences
    if profile.preferences is None:
        profile.preferences = {}

    # Always update to ensure alignment
    # This ensures the profile always reflects the channel preferences
    channel_prefs = dict(channel_preferences) if channel_preferences else {}

    # Explicitly set the preferences dict to trigger SQLAlchemy change detection
    # Make a copy to ensure SQLAlchemy sees it as changed
    new_preferences = dict(profile.preferences) if profile.preferences else {}
    new_preferences["notification_defaults"] = channel_prefs
    profile.preferences = new_preferences
    profile.updated_at = datetime.now(UTC)

    # Mark as modified to ensure SQLAlchemy tracks the change
    from sqlalchemy.orm.attributes import flag_modified

    flag_modified(profile, "preferences")

    db.flush()
