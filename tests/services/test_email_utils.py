"""Tests for email utility helpers."""

from datetime import date

from app.config import settings
from app.db.models import LLMSentimentCategory
from app.services import email_utils


def test_map_sentiment_to_display_handles_enum():
    display = email_utils.map_sentiment_to_display(LLMSentimentCategory.TO_THE_MOON)
    assert display.key == "extreme_positive"
    assert "To the Moon" in display.label
    assert display.emoji == "🚀"


def test_map_sentiment_to_display_defaults_for_unknown():
    display = email_utils.map_sentiment_to_display("unknown-sentiment")
    assert display.key == "neutral"


def test_format_summary_date_uses_timezone(monkeypatch):
    result = email_utils.format_summary_date(date(2024, 11, 10), "UTC")
    assert "2024" in result
    assert "November" in result


def test_format_summary_date_avoids_previous_day(monkeypatch):
    monkeypatch.setattr(settings, "daily_summary_window_timezone", "America/New_York")
    result = email_utils.format_summary_date(date(2024, 11, 10), "America/Los_Angeles")
    assert "November 10" in result


def test_build_unsubscribe_url(monkeypatch):
    monkeypatch.setattr(settings, "app_base_url", "https://example.com/base")
    url = email_utils.build_unsubscribe_url("signed token")
    assert url == "https://example.com/base/unsubscribe?token=signed+token"


def test_normalize_article_payload_filters_invalid():
    assert email_utils.normalize_article_payload({"foo": "bar"}) is None
    parsed = email_utils.normalize_article_payload(
        {
            "title": "Headline",
            "url": "https://example.com",
            "engagement_score": 1.2,
            "source": "Reddit",
        }
    )
    assert parsed is not None
    assert parsed["title"] == "Headline"


def test_verify_unsubscribe_token_valid():
    """Test verifying a valid unsubscribe token."""
    user_id = 123
    token = email_utils.generate_unsubscribe_token(user_id)
    verified_id = email_utils.verify_unsubscribe_token(token)
    assert verified_id == user_id


def test_verify_unsubscribe_token_invalid_type():
    """Test that tokens with wrong type are rejected."""
    import pytest
    from jose import jwt

    from app.config import settings

    # Create token with wrong type
    payload = {
        "sub": "123",
        "type": "session",  # Wrong type
        "exp": 9999999999,
        "iat": 1000000000,
    }
    token = jwt.encode(payload, settings.session_secret_key, algorithm="HS256")
    with pytest.raises(ValueError, match="Invalid token type"):
        email_utils.verify_unsubscribe_token(token)


def test_verify_unsubscribe_token_expired():
    """Test that expired tokens are rejected."""
    from datetime import UTC, datetime, timedelta

    import pytest
    from jose import jwt

    from app.config import settings

    # Create expired token
    payload = {
        "sub": "123",
        "type": "unsubscribe",
        "exp": int((datetime.now(UTC) - timedelta(days=1)).timestamp()),
        "iat": int((datetime.now(UTC) - timedelta(days=2)).timestamp()),
    }
    token = jwt.encode(payload, settings.session_secret_key, algorithm="HS256")
    with pytest.raises(ValueError):
        email_utils.verify_unsubscribe_token(token)
