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
