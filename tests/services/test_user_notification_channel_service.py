"""Tests for user notification channel helpers."""

from app.db.models import User
from app.services.user_notification_channel_service import (
    ensure_email_notification_channel,
)


def create_user(db_session, email: str, provider_id: str) -> User:
    user = User(
        email=email,
        auth_provider="google",
        auth_provider_id=provider_id,
        is_active=True,
        is_deleted=False,
    )
    db_session.add(user)
    db_session.commit()
    return user


def test_ensure_email_notification_channel_creates_entry(db_session):
    """A new channel should be created when one doesn't exist."""
    user = create_user(db_session, "notify@example.com", "notif-1")

    channel, created, updated = ensure_email_notification_channel(
        db_session,
        user_id=user.id,
        email=user.email,
        preferences={"notify_on_surges": True},
    )

    assert created is True
    assert updated is True
    assert channel.channel_type == "email"
    assert channel.channel_value == user.email
    assert channel.preferences == {"notify_on_surges": True}


def test_ensure_email_notification_channel_updates_existing(db_session):
    """Existing channels should be updated when email or prefs change."""
    user = create_user(db_session, "notify2@example.com", "notif-2")

    ensure_email_notification_channel(db_session, user.id, user.email)

    new_email = "updated@example.com"
    user.email = new_email
    db_session.commit()

    channel, created, updated = ensure_email_notification_channel(
        db_session,
        user_id=user.id,
        email=new_email,
        preferences={"notify_on_most_discussed": False},
    )

    assert created is False
    assert updated is True
    assert channel.channel_value == new_email
    assert channel.preferences == {"notify_on_most_discussed": False}
