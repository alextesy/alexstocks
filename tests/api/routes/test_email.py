"""Tests for email routes (unsubscribe and webhooks)."""

import json
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.dto import UserNotificationChannelDTO

client = TestClient(app)


@pytest.fixture
def mock_db_session():
    """Mock database session."""
    return MagicMock()


@pytest.fixture
def mock_user_repo():
    """Mock user repository."""
    repo = MagicMock()
    return repo


def test_unsubscribe_valid_token(mock_user_repo):
    """Test unsubscribe with valid token."""
    from datetime import UTC, datetime

    from app.services.email_utils import generate_unsubscribe_token

    user_id = 123
    token = generate_unsubscribe_token(user_id)

    # Mock channel
    email_channel = UserNotificationChannelDTO(
        id=1,
        user_id=user_id,
        channel_type="email",
        channel_value="test@example.com",
        is_verified=True,
        is_enabled=True,
        preferences={"notify_on_daily_briefing": "true"},
        email_bounced=False,
        bounced_at=None,
        bounce_type=None,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )

    mock_user_repo.get_notification_channels.return_value = [email_channel]
    mock_user_repo.update_notification_channel.return_value = email_channel

    with patch("app.api.routes.email.UserRepository", return_value=mock_user_repo):
        response = client.get(f"/unsubscribe?token={token}")

    assert response.status_code == 200
    assert "successfully unsubscribed" in response.text.lower()
    mock_user_repo.update_notification_channel.assert_called_once_with(
        channel_id=1, is_enabled=False
    )


def test_unsubscribe_invalid_token():
    """Test unsubscribe with invalid token."""
    response = client.get("/unsubscribe?token=invalid-token")
    assert response.status_code == 200
    assert "invalid" in response.text.lower() or "expired" in response.text.lower()


def test_unsubscribe_no_email_channel(mock_user_repo):
    """Test unsubscribe when user has no email channel."""
    from app.services.email_utils import generate_unsubscribe_token

    user_id = 123
    token = generate_unsubscribe_token(user_id)

    mock_user_repo.get_notification_channels.return_value = []

    with patch("app.api.routes.email.UserRepository", return_value=mock_user_repo):
        response = client.get(f"/unsubscribe?token={token}")

    assert response.status_code == 200
    # Should still show success page
    assert "unsubscribed" in response.text.lower()


def test_ses_webhook_subscription_confirmation():
    """Test SNS subscription confirmation."""
    payload = {
        "Type": "SubscriptionConfirmation",
        "SubscribeURL": "https://sns.us-east-1.amazonaws.com/?Action=ConfirmSubscription",
        "TopicArn": "arn:aws:sns:us-east-1:123456789012:test-topic",
    }

    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_response = MagicMock()
        mock_response.read.return_value = b"OK"
        mock_urlopen.return_value = mock_response

        response = client.post("/api/webhooks/ses", json=payload)

    assert response.status_code == 200
    assert "confirmed" in response.text.lower()


def test_ses_webhook_bounce_notification(mock_user_repo):
    """Test processing bounce notification."""
    from datetime import UTC, datetime

    bounce_message = {
        "notificationType": "Bounce",
        "bounce": {
            "bounceType": "Permanent",
            "bounceSubType": "General",
            "bouncedRecipients": [
                {"emailAddress": "bounced@example.com", "status": "5.1.1"}
            ],
        },
    }

    sns_payload = {
        "Type": "Notification",
        "Message": json.dumps(bounce_message),
        "Signature": "test-signature",
        "SigningCertURL": "https://sns.us-east-1.amazonaws.com/cert.pem",
    }

    updated_channel = UserNotificationChannelDTO(
        id=1,
        user_id=123,
        channel_type="email",
        channel_value="bounced@example.com",
        is_verified=True,
        is_enabled=False,  # Disabled due to permanent bounce
        preferences={},
        email_bounced=True,
        bounced_at=datetime.now(UTC),
        bounce_type="Permanent (General)",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )

    mock_user_repo.mark_email_bounced.return_value = updated_channel

    with patch("app.api.routes.email.UserRepository", return_value=mock_user_repo):
        with patch("app.api.routes.email.get_db") as mock_get_db:
            mock_db = MagicMock()
            mock_get_db.return_value = mock_db
            response = client.post("/api/webhooks/ses", json=sns_payload)

    assert response.status_code == 200
    assert "processed" in response.text.lower()
    mock_user_repo.mark_email_bounced.assert_called_once_with(
        email="bounced@example.com",
        bounce_type="Permanent (General)",
        disable_channel=True,
    )
    mock_db.commit.assert_called_once()


def test_ses_webhook_complaint_notification():
    """Test that complaint notifications are skipped."""
    complaint_message = {
        "notificationType": "Complaint",
        "complaint": {
            "complainedRecipients": [{"emailAddress": "complaint@example.com"}],
        },
    }

    sns_payload = {
        "Type": "Notification",
        "Message": json.dumps(complaint_message),
        "Signature": "test-signature",
        "SigningCertURL": "https://sns.us-east-1.amazonaws.com/cert.pem",
    }

    with patch("app.api.routes.email.get_db"):
        response = client.post("/api/webhooks/ses", json=sns_payload)

    assert response.status_code == 200
    assert (
        "not processed" in response.text.lower() or "received" in response.text.lower()
    )


def test_ses_webhook_transient_bounce(mock_user_repo):
    """Test processing transient bounce (should not disable channel)."""
    from datetime import UTC, datetime

    bounce_message = {
        "notificationType": "Bounce",
        "bounce": {
            "bounceType": "Transient",
            "bounceSubType": "MailboxFull",
            "bouncedRecipients": [
                {"emailAddress": "full@example.com", "status": "4.2.2"}
            ],
        },
    }

    sns_payload = {
        "Type": "Notification",
        "Message": json.dumps(bounce_message),
        "Signature": "test-signature",
        "SigningCertURL": "https://sns.us-east-1.amazonaws.com/cert.pem",
    }

    updated_channel = UserNotificationChannelDTO(
        id=1,
        user_id=123,
        channel_type="email",
        channel_value="full@example.com",
        is_verified=True,
        is_enabled=True,  # Still enabled for transient bounce
        preferences={},
        email_bounced=True,
        bounced_at=datetime.now(UTC),
        bounce_type="Transient (MailboxFull)",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )

    mock_user_repo.mark_email_bounced.return_value = updated_channel

    with patch("app.api.routes.email.UserRepository", return_value=mock_user_repo):
        with patch("app.api.routes.email.get_db") as mock_get_db:
            mock_db = MagicMock()
            mock_get_db.return_value = mock_db
            response = client.post("/api/webhooks/ses", json=sns_payload)

    assert response.status_code == 200
    mock_user_repo.mark_email_bounced.assert_called_once_with(
        email="full@example.com",
        bounce_type="Transient (MailboxFull)",
        disable_channel=False,  # Transient bounces don't disable
    )
