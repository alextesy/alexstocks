"""Helpers for managing user notification channels."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import UserNotificationChannel


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

    Returns:
        Tuple of (channel, created_flag, updated_flag).
    """
    stmt = select(UserNotificationChannel).where(
        UserNotificationChannel.user_id == user_id,
        UserNotificationChannel.channel_type == "email",
    )
    channel = db.execute(stmt).scalar_one_or_none()
    now = datetime.now(UTC)

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
        if preferences is not None:
            channel.preferences = preferences
            updated = True

        if updated:
            channel.updated_at = now
            db.flush()
        return channel, False, updated

    channel = UserNotificationChannel(
        user_id=user_id,
        channel_type="email",
        channel_value=email,
        is_verified=True,
        is_enabled=True,
        preferences=preferences,
        created_at=now,
        updated_at=now,
    )
    db.add(channel)
    db.flush()
    return channel, True, True
