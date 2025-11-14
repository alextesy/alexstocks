"""Tests for email service implementations."""

from unittest.mock import MagicMock, patch

import pytest

from app.models.dto import EmailSendResult, UserDTO
from app.services.email_providers.ses import SESEmailService
from app.services.email_service import get_email_service


class TestSESEmailService:
    """Test cases for SES email service."""

    @pytest.fixture
    def ses_service(self):
        """Create SES email service instance."""
        with patch("boto3.client") as mock_client:
            mock_instance = MagicMock()
            mock_client.return_value = mock_instance
            service = SESEmailService()
            service.client = mock_instance  # Override the client with mock
            yield service

    def test_send_email_success(self, ses_service):
        """Test successful email sending."""
        # Mock successful SES response
        mock_response = {"MessageId": "test-message-id-123"}
        ses_service.client.send_email.return_value = mock_response

        result = ses_service.send_email(
            to_email="test@example.com",
            subject="Test Subject",
            html_body="<p>Test HTML</p>",
            text_body="Test text",
        )

        assert isinstance(result, EmailSendResult)
        assert result.success is True
        assert result.message_id == "test-message-id-123"
        assert result.error is None
        assert result.provider == "ses"

        # Verify SES was called correctly
        ses_service.client.send_email.assert_called_once()
        call_args = ses_service.client.send_email.call_args
        assert call_args[1]["Source"] == "noreply@alexstocks.com"
        assert call_args[1]["Destination"]["ToAddresses"] == ["test@example.com"]
        assert call_args[1]["Message"]["Subject"]["Data"] == "Test Subject"

    def test_send_email_with_custom_from(self, ses_service):
        """Test email sending with custom from address and name."""
        ses_service.client.send_email.return_value = {
            "MessageId": "test-message-id-456"
        }

        result = ses_service.send_email(
            to_email="test@example.com",
            subject="Test Subject",
            html_body="<p>Test HTML</p>",
            text_body="Test text",
            from_email="custom@marketpulse.com",
            from_name="Custom Name",
        )

        assert result.success is True
        call_args = ses_service.client.send_email.call_args
        assert call_args[1]["Source"] == "Custom Name <custom@marketpulse.com>"

    def test_send_email_rate_limit_error(self, ses_service):
        """Test handling of SES rate limit errors."""
        from botocore.exceptions import ClientError

        from app.services.email_service import EmailRateLimitError

        # Mock rate limit error
        error_response = {"Error": {"Code": "Throttling", "Message": "Rate exceeded"}}
        ses_service.client.send_email.side_effect = ClientError(
            error_response, "SendEmail"
        )

        with pytest.raises(EmailRateLimitError) as exc_info:
            ses_service.send_email(
                to_email="test@example.com",
                subject="Test Subject",
                html_body="<p>Test HTML</p>",
                text_body="Test text",
            )

        assert "Rate limit exceeded" in str(exc_info.value)

    def test_send_email_permanent_failure(self, ses_service):
        """Test handling of permanent SES failures."""
        from botocore.exceptions import ClientError

        from app.services.email_service import EmailPermanentFailureError

        # Mock permanent error (invalid email format)
        error_response = {
            "Error": {
                "Code": "InvalidParameterValue",
                "Message": "Invalid email address",
            }
        }
        ses_service.client.send_email.side_effect = ClientError(
            error_response, "SendEmail"
        )

        with pytest.raises(EmailPermanentFailureError) as exc_info:
            ses_service.send_email(
                to_email="invalid-email",
                subject="Test Subject",
                html_body="<p>Test HTML</p>",
                text_body="Test text",
            )

        assert "Permanent failure" in str(exc_info.value)

    def test_send_email_retry_on_transient_error(self, ses_service):
        """Test retry logic on transient errors."""
        from botocore.exceptions import ClientError

        # Mock transient error that should be retried
        error_response = {
            "Error": {"Code": "InternalFailure", "Message": "Temporary server error"}
        }
        client_error = ClientError(error_response, "SendEmail")

        # Fail twice, succeed on third attempt
        ses_service.client.send_email.side_effect = [
            client_error,
            client_error,
            {"MessageId": "success-after-retry"},
        ]

        result = ses_service.send_email(
            to_email="test@example.com",
            subject="Test Subject",
            html_body="<p>Test HTML</p>",
            text_body="Test text",
        )

        assert result.success is True
        assert result.message_id == "success-after-retry"
        # Should be called 3 times (initial + 2 retries)
        assert ses_service.client.send_email.call_count == 3

    @patch("time.sleep")  # Mock sleep to speed up tests
    def test_send_email_rate_limit_retry(self, mock_sleep, ses_service):
        """Test retry logic specifically for rate limits."""
        from botocore.exceptions import ClientError

        # Mock rate limit error
        error_response = {"Error": {"Code": "Throttling", "Message": "Rate exceeded"}}
        client_error = ClientError(error_response, "SendEmail")

        # Fail with rate limit twice, succeed on third attempt
        ses_service.client.send_email.side_effect = [
            client_error,
            client_error,
            {"MessageId": "success-after-rate-limit-retry"},
        ]

        result = ses_service.send_email(
            to_email="test@example.com",
            subject="Test Subject",
            html_body="<p>Test HTML</p>",
            text_body="Test text",
        )

        assert result.success is True
        assert result.message_id == "success-after-rate-limit-retry"
        # Should be called 3 times (initial + 2 retries)
        assert ses_service.client.send_email.call_count == 3
        # Should have slept for exponential backoff (1, 2 seconds)
        assert mock_sleep.call_count == 2

    def test_send_summary_email_with_summaries(self, ses_service):
        """Test sending summary email when summaries are available."""
        ses_service.client.send_email.return_value = {"MessageId": "summary-message-id"}

        user = UserDTO(
            id=1,
            email="user@example.com",
            auth_provider_id=None,
            auth_provider=None,
            is_active=True,
            is_deleted=False,
            created_at=None,  # type: ignore
            updated_at=None,  # type: ignore
            deleted_at=None,
        )

        # Mock a ticker summary - simplified for testing
        from app.models.dto import DailyTickerSummaryDTO

        ticker_summaries = [
            DailyTickerSummaryDTO(
                id=1,
                ticker="AAPL",
                summary_date=None,  # type: ignore
                mention_count=10,
                engagement_count=50,
                avg_sentiment=0.2,
                sentiment_stddev=None,
                sentiment_min=None,
                sentiment_max=None,
                top_articles=None,
                llm_summary="Apple showed strong performance today",
                llm_summary_bullets=None,
                llm_sentiment=None,
                llm_model=None,
                llm_version=None,
                created_at=None,  # type: ignore
                updated_at=None,  # type: ignore
            )
        ]

        result = ses_service.send_summary_email(user, ticker_summaries)

        assert result.success is True
        assert result.message_id == "summary-message-id"
        assert result.provider == "ses"

        # Verify the email was sent to the user
        call_args = ses_service.client.send_email.call_args
        assert call_args[1]["Destination"]["ToAddresses"] == ["user@example.com"]
        assert (
            "Market Pulse Daily Summary" in call_args[1]["Message"]["Subject"]["Data"]
        )

    def test_send_summary_email_no_summaries(self, ses_service):
        """Test that no email is sent when there are no summaries."""
        user = UserDTO(
            id=1,
            email="user@example.com",
            auth_provider_id=None,
            auth_provider=None,
            is_active=True,
            is_deleted=False,
            created_at=None,  # type: ignore
            updated_at=None,  # type: ignore
            deleted_at=None,
        )

        # Empty summaries
        ticker_summaries: list = []

        result = ses_service.send_summary_email(user, ticker_summaries)

        assert result.success is True
        assert result.message_id is None  # No email sent, so no message ID
        assert result.error is None
        assert result.provider == "ses"

        # Verify no email was sent (send_email should not be called)
        ses_service.client.send_email.assert_not_called()


class TestEmailServiceFactory:
    """Test cases for email service factory function."""

    @patch("app.config.settings")
    def test_get_email_service_ses(self, mock_settings):
        """Test factory returns SES service when configured."""
        mock_settings.email_provider = "ses"

        service = get_email_service()

        assert isinstance(service, SESEmailService)

    @patch("app.config.settings")
    def test_get_email_service_sendgrid_not_implemented(self, mock_settings):
        """Test factory raises error for unimplemented SendGrid provider."""
        mock_settings.email_provider = "sendgrid"

        with pytest.raises(ValueError, match="SendGrid provider not yet implemented"):
            get_email_service()

    @patch("app.config.settings")
    def test_get_email_service_unknown_provider(self, mock_settings):
        """Test factory raises error for unknown provider."""
        mock_settings.email_provider = "unknown"

        with pytest.raises(ValueError, match="Unsupported email provider: unknown"):
            get_email_service()
