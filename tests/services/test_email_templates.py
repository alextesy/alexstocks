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
        service = EmailTemplateService()

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
                top_articles=[
                    {
                        "title": "Apple tops expectations",
                        "url": "https://example.com/aapl",
                        "engagement_score": 3.2,
                        "source": "Reddit",
                    }
                ],
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
        assert "🚀" not in text  # plain text uses ASCII label
        assert "Apple tops expectations" in html
        assert "Apple tops expectations" in text

    def test_prepare_tickers_filters_and_sorts(self, user, follows):
        """Personalization logic filters to watchlist symbols."""
        service = EmailTemplateService()
        summaries = [
            make_summary("TSLA", summary_id=10, sentiment=LLMSentimentCategory.DOOM),
            make_summary("NVDA", summary_id=11, sentiment=LLMSentimentCategory.BULLISH),
            make_summary("AAPL", summary_id=12, sentiment=LLMSentimentCategory.BULLISH),
        ]

        tickers = service._prepare_tickers(summaries, follows)
        assert [ticker["symbol"] for ticker in tickers] == ["NVDA", "AAPL"]
        assert all("TSLA" != ticker["symbol"] for ticker in tickers)
