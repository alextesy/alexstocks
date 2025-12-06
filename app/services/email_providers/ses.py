"""AWS SES email service implementation."""

import logging
import time
from typing import TYPE_CHECKING

import boto3
from botocore.exceptions import ClientError

from app.config import settings
from app.models.dto import EmailSendResult
from app.services.email_service import (
    EmailPermanentFailureError,
    EmailRateLimitError,
    EmailSendError,
    EmailService,
)
from app.services.email_templates import EmailTemplateService

if TYPE_CHECKING:
    from app.models.dto import (
        DailyTickerSummaryDTO,
        UserDTO,
        UserProfileDTO,
        UserTickerFollowDTO,
        WeeklyDigestContent,
    )

logger = logging.getLogger(__name__)


class SESEmailService(EmailService):
    """AWS SES email service implementation."""

    def __init__(self, template_service: EmailTemplateService | None = None):
        super().__init__("ses")
        self.client = boto3.client(
            "ses",
            region_name=settings.aws_ses_region,
        )
        self.template_service = template_service or EmailTemplateService()

    def send_email(
        self,
        to_email: str,
        subject: str,
        html_body: str,
        text_body: str,
        from_email: str | None = None,
        from_name: str | None = None,
    ) -> EmailSendResult:
        """Send an email using AWS SES.

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
        from_address = from_email or settings.email_from_address
        from_display = from_name or settings.email_from_name

        if from_display and from_display != settings.email_from_name:
            source = f"{from_display} <{from_address}>"
        else:
            source = from_address

        try:
            response = self._send_with_retry(
                source=source,
                to_addresses=[to_email],
                subject=subject,
                html_body=html_body,
                text_body=text_body,
            )

            message_id = response.get("MessageId")
            logger.info(
                "Email sent successfully",
                extra={
                    "provider": self.provider_name,
                    "message_id": message_id,
                    "to_email": to_email,
                    "subject": subject,
                },
            )

            return EmailSendResult(
                success=True,
                message_id=message_id,
                error=None,
                provider=self.provider_name,
            )

        except EmailPermanentFailureError:
            # Re-raise permanent failures without retry
            raise
        except EmailRateLimitError:
            # Re-raise rate limit errors
            raise
        except Exception as e:
            logger.error(
                "Failed to send email",
                extra={
                    "provider": self.provider_name,
                    "to_email": to_email,
                    "subject": subject,
                    "error": str(e),
                },
                exc_info=True,
            )
            return EmailSendResult(
                success=False,
                message_id=None,
                error=str(e),
                provider=self.provider_name,
            )

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
            user_ticker_follows: Optional watchlist data for ordering
            unsubscribe_token: Signed token for unsubscribe link

        Returns:
            EmailSendResult with success status and metadata
        """
        # Don't send email if there are no summaries for today
        if not ticker_summaries:
            logger.info(
                "Skipping email send - no summaries available for today",
                extra={"user_id": user.id, "user_email": user.email},
            )
            return EmailSendResult(
                success=True,
                message_id=None,
                error=None,
                provider=self.provider_name,
            )

        subject = "AlexStocks Daily Summary"
        if user_profile and user_ticker_follows is not None and unsubscribe_token:
            html_body, text_body = self.template_service.render_daily_briefing(
                user=user,
                user_profile=user_profile,
                ticker_summaries=ticker_summaries,
                user_ticker_follows=user_ticker_follows,
                unsubscribe_token=unsubscribe_token,
            )
        else:
            html_body, text_body = self.template_service.render_basic_summary(
                ticker_summaries
            )

        return self.send_email(
            to_email=user.email,
            subject=subject,
            html_body=html_body,
            text_body=text_body,
        )

    def send_weekly_digest(
        self,
        user: "UserDTO",
        digest_content: "WeeklyDigestContent",
        *,
        user_profile: "UserProfileDTO | None" = None,
        unsubscribe_token: str | None = None,
    ) -> EmailSendResult:
        """Send a weekly digest email to a user.

        Args:
            user: User to send email to
            digest_content: Weekly digest content with synthesized summaries
            user_profile: Optional user profile for personalization
            unsubscribe_token: Signed token for unsubscribe link

        Returns:
            EmailSendResult with success status and metadata
        """
        # Don't send if no tickers to report
        if digest_content.total_tickers == 0:
            logger.info(
                "Skipping weekly digest - no tickers with data",
                extra={"user_id": user.id, "user_email": user.email},
            )
            return EmailSendResult(
                success=True,
                message_id=None,
                error=None,
                provider=self.provider_name,
            )

        # Build subject line with date range
        week_range = (
            f"{digest_content.week_start.strftime('%b %d')}-"
            f"{digest_content.week_end.strftime('%d')}"
        )
        subject = f"Your Weekly Market Digest - {week_range}"

        if user_profile and unsubscribe_token:
            html_body, text_body = self.template_service.render_weekly_digest(
                user=user,
                user_profile=user_profile,
                digest_content=digest_content,
                unsubscribe_token=unsubscribe_token,
            )
        else:
            # Fallback: basic rendering
            html_body = f"<h1>Weekly Digest</h1><p>{digest_content.headline}</p>"
            text_body = f"Weekly Digest\n\n{digest_content.headline}"

        logger.info(
            "Sending weekly digest email",
            extra={
                "user_id": user.id,
                "user_email": user.email,
                "ticker_count": digest_content.total_tickers,
                "week_start": digest_content.week_start.isoformat(),
                "week_end": digest_content.week_end.isoformat(),
            },
        )

        return self.send_email(
            to_email=user.email,
            subject=subject,
            html_body=html_body,
            text_body=text_body,
        )

    def _send_with_retry(
        self,
        source: str,
        to_addresses: list[str],
        subject: str,
        html_body: str,
        text_body: str,
        max_retries: int = 3,
    ) -> dict:
        """Send email with exponential backoff retry logic.

        Args:
            source: From email address
            to_addresses: List of recipient email addresses
            subject: Email subject
            html_body: HTML email body
            text_body: Plain text email body
            max_retries: Maximum number of retry attempts

        Returns:
            SES response dictionary

        Raises:
            EmailSendError: For general send failures
            EmailRateLimitError: For rate limiting
            EmailPermanentFailureError: For permanent failures
        """
        last_exception = None

        for attempt in range(max_retries + 1):
            try:
                response = self.client.send_email(
                    Source=source,
                    Destination={"ToAddresses": to_addresses},
                    Message={
                        "Subject": {"Data": subject, "Charset": "UTF-8"},
                        "Body": {
                            "Html": {"Data": html_body, "Charset": "UTF-8"},
                            "Text": {"Data": text_body, "Charset": "UTF-8"},
                        },
                    },
                )
                return response

            except ClientError as e:
                error_code = e.response.get("Error", {}).get("Code", "")
                error_message = e.response.get("Error", {}).get("Message", str(e))
                last_exception = e

                if self._is_permanent_failure(error_code):
                    logger.warning(
                        "Permanent email failure",
                        extra={
                            "provider": self.provider_name,
                            "error_code": error_code,
                            "error_message": error_message,
                            "attempt": attempt + 1,
                        },
                    )
                    raise EmailPermanentFailureError(
                        f"Permanent failure: {error_message}",
                        provider=self.provider_name,
                        original_error=e,
                    ) from e

                if self._is_rate_limit_error(error_code):
                    if attempt < max_retries:
                        wait_time = 2**attempt  # Exponential backoff
                        logger.warning(
                            "Rate limit hit, retrying",
                            extra={
                                "provider": self.provider_name,
                                "error_code": error_code,
                                "wait_time": wait_time,
                                "attempt": attempt + 1,
                            },
                        )
                        time.sleep(wait_time)
                        continue
                    else:
                        raise EmailRateLimitError(
                            f"Rate limit exceeded: {error_message}",
                            provider=self.provider_name,
                            original_error=e,
                        ) from e

                # For other errors, retry if we have attempts left
                if attempt < max_retries:
                    wait_time = 2**attempt
                    logger.warning(
                        "Transient error, retrying",
                        extra={
                            "provider": self.provider_name,
                            "error_code": error_code,
                            "error_message": error_message,
                            "wait_time": wait_time,
                            "attempt": attempt + 1,
                        },
                    )
                    time.sleep(wait_time)
                    continue

                # Final attempt failed
                break

        # All retries exhausted
        raise EmailSendError(
            f"Failed to send email after {max_retries + 1} attempts: {str(last_exception)}",
            provider=self.provider_name,
            original_error=last_exception,
        )

    def _is_permanent_failure(self, error_code: str) -> bool:
        """Check if an SES error code indicates permanent failure.

        Args:
            error_code: SES error code

        Returns:
            True if the error is permanent
        """
        permanent_errors = {
            "InvalidParameterValue",
            "InvalidParameterCombination",
            "MalformedInput",
            "MessageRejected",  # Usually due to content issues
        }
        return error_code in permanent_errors

    def _is_rate_limit_error(self, error_code: str) -> bool:
        """Check if an SES error code indicates rate limiting.

        Args:
            error_code: SES error code

        Returns:
            True if the error is due to rate limiting
        """
        return error_code in {"Throttling", "ThrottlingException"}

    def send_raw_email(
        self,
        to_email: str,
        raw_message: bytes,
        from_email: str | None = None,
    ) -> EmailSendResult:
        """Send a raw MIME email message using AWS SES.

        Args:
            to_email: Recipient email address
            raw_message: Raw MIME message bytes
            from_email: Override from email address (not used, extracted from message)

        Returns:
            EmailSendResult with success status and metadata
        """
        from_address = from_email or settings.email_from_address

        try:
            response = self.client.send_raw_email(
                Source=from_address,
                Destinations=[to_email],
                RawMessage={"Data": raw_message},
            )

            message_id = response.get("MessageId")
            logger.info(
                "Raw email sent successfully",
                extra={
                    "provider": self.provider_name,
                    "message_id": message_id,
                    "to_email": to_email,
                },
            )

            return EmailSendResult(
                success=True,
                message_id=message_id,
                error=None,
                provider=self.provider_name,
            )

        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "")
            error_message = e.response.get("Error", {}).get("Message", str(e))

            if self._is_permanent_failure(error_code):
                logger.warning(
                    "Permanent email failure",
                    extra={
                        "provider": self.provider_name,
                        "error_code": error_code,
                        "error_message": error_message,
                        "to_email": to_email,
                    },
                )
                raise EmailPermanentFailureError(
                    f"Permanent failure: {error_message}",
                    provider=self.provider_name,
                    original_error=e,
                ) from e

            if self._is_rate_limit_error(error_code):
                raise EmailRateLimitError(
                    f"Rate limit exceeded: {error_message}",
                    provider=self.provider_name,
                    original_error=e,
                ) from e

            logger.error(
                "Failed to send raw email",
                extra={
                    "provider": self.provider_name,
                    "to_email": to_email,
                    "error": str(e),
                },
                exc_info=True,
            )
            return EmailSendResult(
                success=False,
                message_id=None,
                error=str(e),
                provider=self.provider_name,
            )
        except Exception as e:
            logger.error(
                "Failed to send raw email",
                extra={
                    "provider": self.provider_name,
                    "to_email": to_email,
                    "error": str(e),
                },
                exc_info=True,
            )
            return EmailSendResult(
                success=False,
                message_id=None,
                error=str(e),
                provider=self.provider_name,
            )
