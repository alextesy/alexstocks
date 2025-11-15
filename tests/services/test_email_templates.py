"""Tests for the email template rendering service."""

from datetime import UTC, date, datetime

import pytest

from app.config import settings
from app.db.models import LLMSentimentCategory
from app.models.dto import (
    DailyTickerSummaryDTO,
    UserDTO,
    UserProfileDTO,
    UserTickerFollowDTO,
)
from app.services.email_templates import EmailTemplateService


def make_summary(
    ticker: str,
    *,
    summary_id: int,
    sentiment: LLMSentimentCategory | None = None,
    top_articles: list | None = None,
) -> DailyTickerSummaryDTO:
    """Helper to construct ticker summary DTOs for tests."""
    now = datetime.now(UTC)
    return DailyTickerSummaryDTO(
        id=summary_id,
        ticker=ticker,
        summary_date=date(2024, 11, 10),
        mention_count=25,
        engagement_count=120,
        avg_sentiment=0.42,
        sentiment_stddev=None,
        sentiment_min=None,
        sentiment_max=None,
        top_articles=top_articles,
        llm_summary=f"{ticker} summary text.",
        llm_summary_bullets=["Strong momentum", "Retail interest rising"],
        llm_sentiment=sentiment,
        llm_model="gpt-test",
        llm_version="1",
        created_at=now,
        updated_at=now,
    )


@pytest.fixture
def user():
    return UserDTO(
        id=1,
        email="user@example.com",
        auth_provider_id=None,
        auth_provider=None,
        is_active=True,
        is_deleted=False,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
        deleted_at=None,
    )


@pytest.fixture
def profile(user):
    return UserProfileDTO(
        user_id=user.id,
        display_name="Alex",
        timezone="America/New_York",
        avatar_url=None,
        bio=None,
        preferences=None,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


@pytest.fixture
def follows(user):
    return [
        UserTickerFollowDTO(
            id=1,
            user_id=user.id,
            ticker="AAPL",
            ticker_name="Apple Inc.",
            order=2,
        ),
        UserTickerFollowDTO(
            id=2,
            user_id=user.id,
            ticker="NVDA",
            ticker_name="NVIDIA",
            order=1,
        ),
    ]


class TestEmailTemplateService:
    """Template rendering cases."""

    def test_render_daily_briefing_with_watchlist(
        self, monkeypatch, user, profile, follows
    ):
        """HTML/text rendering uses personalized data."""
        monkeypatch.setattr(settings, "app_base_url", "https://example.com")
        published_at = datetime(2024, 11, 10, 15, tzinfo=UTC)
        article_metadata = {
            1: {
                "title": "Thread title",
                "url": "https://example.com/aapl",
                "engagement_score": 3.2,
                "source": "reddit_comment",
                "text": "Apple comment preview text that should show up.",
                "published_at": published_at,
            }
        }

        def loader(ids):
            return {
                article_id: article_metadata[article_id]
                for article_id in ids
                if article_id in article_metadata
            }

        service = EmailTemplateService(article_loader=loader)
        monkeypatch.setattr(
            service, "_get_participant_count", lambda *args, **kwargs: 12
        )
        monkeypatch.setattr(service, "_get_last_price", lambda *args, **kwargs: 123.45)

        summaries = [
            make_summary(
                "NVDA",
                summary_id=1,
                sentiment=LLMSentimentCategory.BULLISH,
            ),
            make_summary(
                "AAPL",
                summary_id=2,
                sentiment=LLMSentimentCategory.TO_THE_MOON,
                top_articles=[1],
            ),
            make_summary("TSLA", summary_id=3, sentiment=LLMSentimentCategory.BEARISH),
        ]

        html, text = service.render_daily_briefing(
            user=user,
            user_profile=profile,
            ticker_summaries=summaries,
            user_ticker_follows=follows,
            unsubscribe_token="signed-token",
        )

        assert "Apple Inc." in html
        assert "NVIDIA" in html
        assert "TSLA" not in html  # not part of watchlist selection
        assert "unsubscribe?token=signed-token" in html
        assert "https://example.com" in html
        assert "To the Moon" in html
        assert "🚀" in html
        assert "🚀" not in text  # plain text uses ASCII label
        assert "Apple comment preview text" in html
        assert "Thread title" in html
        assert "$123.45" in html
        assert "Participants" in html
        assert "Apple comment preview text" in text

    def test_prepare_tickers_filters_and_sorts(self, user, follows, monkeypatch):
        """Personalization logic filters to watchlist symbols."""
        service = EmailTemplateService()
        monkeypatch.setattr(
            service, "_get_participant_count", lambda *args, **kwargs: 0
        )
        monkeypatch.setattr(service, "_get_last_price", lambda *args, **kwargs: None)
        monkeypatch.setattr(service, "_article_loader", lambda ids: {})
        summaries = [
            make_summary("TSLA", summary_id=10, sentiment=LLMSentimentCategory.DOOM),
            make_summary("NVDA", summary_id=11, sentiment=LLMSentimentCategory.BULLISH),
            make_summary("AAPL", summary_id=12, sentiment=LLMSentimentCategory.BULLISH),
        ]

        tickers = service._prepare_tickers(summaries, follows)
        assert [ticker["symbol"] for ticker in tickers] == ["NVDA", "AAPL"]
        assert all("TSLA" != ticker["symbol"] for ticker in tickers)

    def test_summary_window_bounds_uses_custom_hours(self, monkeypatch):
        """Participant windows align with daily summary configuration."""
        monkeypatch.setattr(
            settings, "daily_summary_window_timezone", "America/New_York"
        )
        monkeypatch.setattr(settings, "daily_summary_window_start_hour", 7)
        monkeypatch.setattr(settings, "daily_summary_window_end_hour", 19)
        service = EmailTemplateService()

        start, end = service._summary_window_bounds(date(2024, 5, 2))

        assert start == datetime(2024, 5, 2, 11, tzinfo=UTC)
        assert end == datetime(2024, 5, 2, 23, tzinfo=UTC)

    def test_summary_window_bounds_handles_cross_midnight(self, monkeypatch):
        """Cross-midnight windows carry the end into the next day."""
        monkeypatch.setattr(
            settings, "daily_summary_window_timezone", "America/New_York"
        )
        monkeypatch.setattr(settings, "daily_summary_window_start_hour", 20)
        monkeypatch.setattr(settings, "daily_summary_window_end_hour", 6)
        service = EmailTemplateService()

        start, end = service._summary_window_bounds(date(2024, 1, 15))

        assert start == datetime(2024, 1, 16, 1, tzinfo=UTC)
        assert end == datetime(2024, 1, 16, 11, tzinfo=UTC)

    def test_normalize_articles_filters_to_window(self, monkeypatch):
        """Top articles respect the configured daily summary window."""
        monkeypatch.setattr(
            settings, "daily_summary_window_timezone", "America/New_York"
        )
        monkeypatch.setattr(settings, "daily_summary_window_start_hour", 7)
        monkeypatch.setattr(settings, "daily_summary_window_end_hour", 19)

        published_inside = datetime(2024, 5, 2, 15, tzinfo=UTC)
        published_too_early = datetime(2024, 5, 2, 9, tzinfo=UTC)
        published_too_late = datetime(2024, 5, 2, 23, 30, tzinfo=UTC)

        articles = {
            1: {
                "title": "Inside Window",
                "url": "https://example.com/inside",
                "engagement_score": 1.2,
                "source": "reddit",
                "text": "Inside window text",
                "published_at": published_inside,
            },
            2: {
                "title": "Too Early",
                "url": "https://example.com/early",
                "engagement_score": 0.5,
                "source": "reddit",
                "text": "Early text",
                "published_at": published_too_early,
            },
            3: {
                "title": "Too Late",
                "url": "https://example.com/late",
                "engagement_score": 0.8,
                "source": "reddit",
                "text": "Late text",
                "published_at": published_too_late,
            },
        }

        service = EmailTemplateService(article_loader=lambda ids: articles)
        normalized = service._normalize_articles([1, 2, 3], date(2024, 5, 2))

        assert len(normalized) == 1
        assert normalized[0]["title"] == "Inside Window"

    def test_normalize_articles_handles_cross_midnight_window(self, monkeypatch):
        """Articles after midnight are included when window spans days."""
        monkeypatch.setattr(
            settings, "daily_summary_window_timezone", "America/New_York"
        )
        monkeypatch.setattr(settings, "daily_summary_window_start_hour", 20)
        monkeypatch.setattr(settings, "daily_summary_window_end_hour", 6)

        inside = datetime(2024, 1, 16, 3, tzinfo=UTC)
        before_window = datetime(2024, 1, 15, 23, tzinfo=UTC)
        after_window = datetime(2024, 1, 16, 15, tzinfo=UTC)

        articles = {
            10: {
                "title": "Night Session",
                "url": "https://example.com/night",
                "engagement_score": 1.5,
                "source": "reddit",
                "text": "Night text",
                "published_at": inside,
            },
            11: {
                "title": "Before Window",
                "url": "https://example.com/before",
                "engagement_score": 0.2,
                "source": "reddit",
                "text": "Before text",
                "published_at": before_window,
            },
            12: {
                "title": "After Window",
                "url": "https://example.com/after",
                "engagement_score": 0.3,
                "source": "reddit",
                "text": "After text",
                "published_at": after_window,
            },
        }

        service = EmailTemplateService(article_loader=lambda ids: articles)
        normalized = service._normalize_articles([10, 11, 12], date(2024, 1, 15))

        assert [article["title"] for article in normalized] == ["Night Session"]
