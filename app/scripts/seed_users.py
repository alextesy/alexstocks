"""Seed sample users for local testing (disabled in production)."""

import logging
from typing import Any

from app.config import settings
from app.db.session import SessionLocal
from app.models.dto import (
    UserCreateDTO,
    UserNotificationChannelCreateDTO,
    UserProfileCreateDTO,
    UserTickerFollowCreateDTO,
)
from app.repos.user_repo import UserRepository

logger = logging.getLogger(__name__)


def seed_users() -> None:
    """Seed sample users for local testing."""
    # Safety check: prevent running in production
    if settings.environment == "production":
        logger.warning("❌ Seed script disabled in production environment")
        return

    logger.info("🌱 Seeding sample users...")

    with SessionLocal() as session:
        repo = UserRepository(session)

        # Sample users
        sample_users: list[dict[str, Any]] = [
            {
                "email": "alice@example.com",
                "auth_provider": "google",
                "auth_provider_id": "google_alice_123",
                "profile": {
                    "display_name": "Alice Johnson",
                    "timezone": "America/New_York",
                    "bio": "Tech enthusiast and investor",
                },
                "follows": ["AAPL", "GOOGL", "MSFT"],
            },
            {
                "email": "bob@example.com",
                "auth_provider": "google",
                "auth_provider_id": "google_bob_456",
                "profile": {
                    "display_name": "Bob Smith",
                    "timezone": "America/Los_Angeles",
                    "bio": "Day trader",
                },
                "follows": ["TSLA", "NVDA", "AMD"],
            },
            {
                "email": "charlie@example.com",
                "auth_provider": "google",
                "auth_provider_id": "google_charlie_789",
                "profile": {
                    "display_name": "Charlie Davis",
                    "timezone": "UTC",
                    "bio": "Long-term investor",
                },
                "follows": ["SPY", "QQQ", "AAPL", "AMZN"],
            },
        ]

        created_count = 0
        for user_data in sample_users:
            # Check if user already exists
            existing = repo.get_user_by_email(user_data["email"])
            if existing:
                logger.info(f"  ⏭️  User {user_data['email']} already exists, skipping")
                continue

            # Create user
            user_dto = repo.create_user(
                UserCreateDTO(
                    email=user_data["email"],
                    auth_provider=user_data["auth_provider"],
                    auth_provider_id=user_data["auth_provider_id"],
                )
            )
            logger.info(f"  ✅ Created user: {user_data['email']} (ID: {user_dto.id})")

            # Create profile
            profile_data = user_data["profile"]
            repo.create_profile(
                UserProfileCreateDTO(
                    user_id=user_dto.id,
                    display_name=profile_data["display_name"],
                    timezone=profile_data["timezone"],
                    bio=profile_data.get("bio"),
                )
            )
            logger.info(f"     • Created profile for {user_data['email']}")

            # Create email notification channel
            repo.create_notification_channel(
                UserNotificationChannelCreateDTO(
                    user_id=user_dto.id,
                    channel_type="email",
                    channel_value=user_data["email"],
                    is_verified=True,
                    is_enabled=True,
                )
            )
            logger.info("     • Created email notification channel")

            # Create ticker follows
            for ticker in user_data["follows"]:
                repo.create_ticker_follow(
                    UserTickerFollowCreateDTO(
                        user_id=user_dto.id,
                        ticker=ticker,
                        notify_on_signals=True,
                        notify_on_price_change=False,
                    )
                )
            logger.info(f"     • Created {len(user_data['follows'])} ticker follows")

            created_count += 1

        # Commit all changes
        session.commit()
        logger.info(f"✅ Seeded {created_count} users successfully")


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
    )
    seed_users()
