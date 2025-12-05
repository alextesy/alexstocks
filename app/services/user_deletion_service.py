"""Service for handling user account deletion."""

import logging
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.repos.user_repo import UserRepository
from app.services.slack_service import SlackService

logger = logging.getLogger(__name__)


class UserDeletionService:
    """Service for orchestrating user account deletion."""

    def __init__(self, db: Session, slack_service: SlackService | None = None):
        """Initialize deletion service.

        Args:
            db: Database session
            slack_service: Slack service for notifications (optional)
        """
        self.db = db
        self.slack_service = slack_service or SlackService()

    def delete_user(self, user_id: int, email: str) -> bool:
        """Delete a user account and all associated data.

        This method:
        1. Validates user exists
        2. Wraps hard_delete_user in transaction with rollback on error
        3. Logs deletion event with user_id/email/timestamp/method/status
        4. Sends Slack notification on success
        5. Returns boolean success status

        Args:
            user_id: User ID to delete
            email: User email address (for logging and notifications)

        Returns:
            True if deletion succeeded, False otherwise
        """
        repo = UserRepository(self.db)

        # Validate user exists
        user = repo.get_user_by_id(user_id, include_deleted=True)
        if not user:
            logger.warning(
                "user_deletion_failed_user_not_found",
                extra={
                    "user_id": user_id,
                    "email": email,
                    "timestamp": datetime.now(UTC).isoformat(),
                    "method": "delete_user",
                    "status": "user_not_found",
                },
            )
            return False

        # Log deletion attempt
        logger.info(
            "user_deletion_started",
            extra={
                "user_id": user_id,
                "email": email,
                "timestamp": datetime.now(UTC).isoformat(),
                "method": "delete_user",
                "status": "started",
            },
        )

        try:
            # Hard delete user (CASCADE handles related records)
            success = repo.hard_delete_user(user_id)

            if not success:
                logger.error(
                    "user_deletion_failed",
                    extra={
                        "user_id": user_id,
                        "email": email,
                        "timestamp": datetime.now(UTC).isoformat(),
                        "method": "delete_user",
                        "status": "hard_delete_failed",
                    },
                )
                self.db.rollback()
                return False

            # Commit transaction
            self.db.commit()

            # Log successful deletion
            logger.info(
                "user_deletion_completed",
                extra={
                    "user_id": user_id,
                    "email": email,
                    "timestamp": datetime.now(UTC).isoformat(),
                    "method": "delete_user",
                    "status": "success",
                },
            )

            # Send Slack notification (non-blocking - don't fail if Slack fails)
            try:
                self.slack_service.notify_user_deleted(
                    user_id=user_id,
                    email=email,
                )
            except Exception as e:
                logger.warning(
                    "user_deletion_slack_notification_failed",
                    extra={
                        "user_id": user_id,
                        "email": email,
                        "error": str(e),
                    },
                )
                # Don't fail deletion if Slack notification fails

            return True

        except Exception as e:
            # Rollback on any error
            logger.error(
                "user_deletion_error",
                extra={
                    "user_id": user_id,
                    "email": email,
                    "timestamp": datetime.now(UTC).isoformat(),
                    "method": "delete_user",
                    "status": "error",
                    "error": str(e),
                },
            )
            self.db.rollback()
            return False
