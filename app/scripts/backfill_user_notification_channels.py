"""Backfill script to ensure email notification channels exist for all users."""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.db.models import User, UserProfile
from app.db.session import SessionLocal
from app.services.user_notification_channel_service import (
    ensure_email_notification_channel,
)

logger = logging.getLogger(__name__)


def backfill_channels(db: Session) -> tuple[int, int, int]:
    """Backfill user notification channels.

    Args:
        db: Database session.

    Returns:
        Tuple of (total_users, created_channels, updated_channels).
    """
    users = (
        db.query(User)
        .filter(User.is_deleted == False)  # noqa: E712 - SQLAlchemy boolean
        .all()
    )
    created = 0
    updated = 0
    for user in users:
        # Get user profile to extract notification_defaults
        profile = db.get(UserProfile, user.id)
        notification_defaults = None
        if profile and profile.preferences and isinstance(profile.preferences, dict):
            notification_defaults = profile.preferences.get("notification_defaults")

        _, created_flag, updated_flag = ensure_email_notification_channel(
            db,
            user_id=user.id,
            email=user.email,
            preferences=notification_defaults,
        )
        if created_flag:
            created += 1
        elif updated_flag:
            updated += 1

    return len(users), created, updated


def main() -> None:
    """Run the backfill process and log summary."""
    logging.basicConfig(level=logging.INFO)
    db = SessionLocal()
    try:
        total, created, updated = backfill_channels(db)
        db.commit()
        logger.info(
            "user_notification_channels_backfill_complete",
            extra={
                "total_users": total,
                "created_channels": created,
                "updated_channels": updated,
            },
        )
        print(
            f"Processed {total} users. Created {created} channels, updated {updated} channels."
        )
    except Exception:
        db.rollback()
        logger.exception("user_notification_channels_backfill_failed")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
