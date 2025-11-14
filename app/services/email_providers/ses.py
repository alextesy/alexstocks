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

if TYPE_CHECKING:
    from app.models.dto import DailyTickerSummaryDTO, UserDTO

logger = logging.getLogger(__name__)


class SESEmailService(EmailService):
    """AWS SES email service implementation."""

    def __init__(self):
        super().__init__("ses")
        self.client = boto3.client(
            "ses",
            region_name=settings.aws_ses_region,
        )

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
    ) -> EmailSendResult:
        """Send a daily summary email to a user.

        Args:
            user: User to send email to
            ticker_summaries: List of ticker summaries for the day

        Returns:
            EmailSendResult with success status and metadata
        """
        subject = "Market Pulse Daily Summary"
        html_body, text_body = self._format_summary_email(ticker_summaries)

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

    def _format_summary_email(
        self,
        ticker_summaries: list["DailyTickerSummaryDTO"],
    ) -> tuple[str, str]:
        """Format ticker summaries into HTML and text email bodies.

        Args:
            ticker_summaries: List of ticker summaries

        Returns:
            Tuple of (html_body, text_body)
        """
        if not ticker_summaries:
            html_body = "<p>No market summaries available for today.</p>"
            text_body = "No market summaries available for today."
            return html_body, text_body

        # Sort by engagement (most discussed first)
        sorted_summaries = sorted(
            ticker_summaries,
            key=lambda x: x.engagement_count,
            reverse=True,
        )

        # HTML version
        html_parts = [
            "<h1>Market Pulse Daily Summary</h1>",
            "<p>Here's your daily market intelligence:</p>",
            "<table style='border-collapse: collapse; width: 100%;'>",
            "<tr style='background-color: #f2f2f2;'>",
            "<th style='border: 1px solid #ddd; padding: 8px; text-align: left;'>Ticker</th>",
            "<th style='border: 1px solid #ddd; padding: 8px; text-align: left;'>Mentions</th>",
            "<th style='border: 1px solid #ddd; padding: 8px; text-align: left;'>Engagement</th>",
            "<th style='border: 1px solid #ddd; padding: 8px; text-align: left;'>Sentiment</th>",
            "</tr>",
        ]

        text_parts = [
            "Market Pulse Daily Summary",
            "=" * 30,
            "",
            "Here's your daily market intelligence:",
            "",
            f"{'Ticker':<10} {'Mentions':<10} {'Engagement':<12} {'Sentiment'}",
            "-" * 60,
        ]

        for summary in sorted_summaries:
            sentiment_display = "N/A"
            if summary.llm_sentiment:
                sentiment_display = summary.llm_sentiment.value.title()

            html_parts.extend(
                [
                    "<tr>",
                    f"<td style='border: 1px solid #ddd; padding: 8px;'>{summary.ticker}</td>",
                    f"<td style='border: 1px solid #ddd; padding: 8px;'>{summary.mention_count}</td>",
                    f"<td style='border: 1px solid #ddd; padding: 8px;'>{summary.engagement_count}</td>",
                    f"<td style='border: 1px solid #ddd; padding: 8px;'>{sentiment_display}</td>",
                    "</tr>",
                ]
            )

            text_parts.append(
                f"{summary.ticker:<10} {summary.mention_count:<10} {summary.engagement_count:<12} {sentiment_display}"
            )

            # Add summary text if available
            if summary.llm_summary:
                html_parts.append(
                    f"<tr><td colspan='4' style='border: 1px solid #ddd; padding: 8px;'><strong>Summary:</strong> {summary.llm_summary}</td></tr>"
                )
                text_parts.append(f"Summary: {summary.llm_summary}")
                text_parts.append("")

        html_parts.extend(["</table>", "<p>Stay informed with Market Pulse!</p>"])
        text_parts.extend(["", "Stay informed with Market Pulse!"])

        html_body = "\n".join(html_parts)
        text_body = "\n".join(text_parts)

        return html_body, text_body
