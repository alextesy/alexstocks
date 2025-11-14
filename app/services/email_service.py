"""Email service abstraction layer with provider adapters."""

import logging
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from app.models.dto import EmailSendResult

if TYPE_CHECKING:
    from app.models.dto import (
        DailyTickerSummaryDTO,
        UserDTO,
        UserProfileDTO,
        UserTickerFollowDTO,
    )

logger = logging.getLogger(__name__)


class EmailError(Exception):
    """Base exception for email service errors."""

    pass


class EmailSendError(EmailError):
    """Exception raised when email sending fails."""

    def __init__(
        self, message: str, provider: str, original_error: Exception | None = None
    ):
        super().__init__(message)
        self.provider = provider
        self.original_error = original_error


class EmailRateLimitError(EmailSendError):
    """Exception raised when email rate limits are exceeded."""

    pass


class EmailPermanentFailureError(EmailSendError):
    """Exception raised for permanent email failures (invalid email, etc.)."""

    pass


class EmailService(ABC):
    """Abstract base class for email service providers."""

    def __init__(self, provider_name: str):
        self.provider_name = provider_name

    @abstractmethod
    def send_email(
        self,
        to_email: str,
        subject: str,
        html_body: str,
        text_body: str,
        from_email: str | None = None,
        from_name: str | None = None,
    ) -> EmailSendResult:
        """Send an email message.

        Args:
            to_email: Recipient email address
            subject: Email subject
            html_body: HTML email body
            text_body: Plain text email body
            from_email: Override from email address
            from_name: Override from name

        Returns:
            EmailSendResult with success status and metadata
        """
        pass

    @abstractmethod
    def send_summary_email(
        self,
        user: "UserDTO",
        ticker_summaries: list["DailyTickerSummaryDTO"],
        *,
        user_profile: "UserProfileDTO | None" = None,
        user_ticker_follows: list["UserTickerFollowDTO"] | None = None,
        unsubscribe_token: str | None = None,
    ) -> EmailSendResult:
        """Send a daily summary email to a user.

        Args:
            user: User to send email to
            ticker_summaries: List of ticker summaries for the day
            user_profile: Optional user profile for personalization
            user_ticker_follows: Optional watchlist ordering to personalize content
            unsubscribe_token: Signed token for unsubscribe link

        Returns:
            EmailSendResult with success status and metadata
        """
        pass


def get_email_service() -> EmailService:
    """Factory function to get the configured email service.

    Returns:
        EmailService instance based on configuration

    Raises:
        ValueError: If the configured provider is not supported
    """
    from app.config import settings

    if settings.email_provider == "ses":
        from app.services.email_providers.ses import SESEmailService

        return SESEmailService()
    elif settings.email_provider == "sendgrid":
        # TODO: Implement SendGrid provider when needed
        raise ValueError("SendGrid provider not yet implemented")
    else:
        raise ValueError(f"Unsupported email provider: {settings.email_provider}")
