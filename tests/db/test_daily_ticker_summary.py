"""Tests for the DailyTickerSummary repository."""

from datetime import date, timedelta

import pytest

from app.db.models import LLMSentimentCategory, Ticker
from app.models.dto import DailyTickerSummaryUpsertDTO
from app.repos.summary_repo import DailyTickerSummaryRepository


@pytest.fixture
def repo(db_session):
    """Return a repository bound to the test session."""

    return DailyTickerSummaryRepository(db_session)


def _ensure_ticker(db_session, symbol: str = "AAPL") -> Ticker:
    ticker = db_session.get(Ticker, symbol)
    if ticker is None:
        ticker = Ticker(symbol=symbol, name=f"{symbol} Inc.")
        db_session.add(ticker)
        db_session.commit()
    return ticker


def test_upsert_creates_and_updates_summary(db_session, repo):
    """Upserting should insert new rows and update existing ones."""

    _ensure_ticker(db_session, "AAPL")
    dto = DailyTickerSummaryUpsertDTO(
        ticker="AAPL",
        summary_date=date(2024, 1, 1),
        mention_count=120,
        engagement_count=500,
        avg_sentiment=0.45,
        sentiment_stddev=0.1,
        sentiment_min=-0.2,
        sentiment_max=0.9,
        top_articles=[101],
        llm_summary="Apple sees strong retail interest",
        llm_summary_bullets=["Retail flow up", "High optimism"],
        llm_model="gpt-test",
        llm_version="1.0",
    )

    created = repo.upsert_summary(dto)
    assert created.id is not None
    assert created.mention_count == 120
    original_updated_at = created.updated_at

    updated = repo.upsert_summary(
        DailyTickerSummaryUpsertDTO(
            ticker="AAPL",
            summary_date=date(2024, 1, 1),
            mention_count=200,
            engagement_count=750,
            avg_sentiment=0.5,
            sentiment_stddev=0.15,
            sentiment_min=-0.1,
            sentiment_max=0.95,
            top_articles=[101, 202],
            llm_summary="Retail interest continues to climb",
            llm_summary_bullets=["Mentions up"],
            llm_model="gpt-test",
            llm_version="1.1",
        )
    )

    assert updated.id == created.id
    assert updated.mention_count == 200
    assert updated.engagement_count == 750
    assert updated.llm_version == "1.1"
    assert updated.updated_at >= original_updated_at


def test_get_summaries_filters_and_orders(db_session, repo):
    """Fetching summaries should respect date filters and ordering."""

    _ensure_ticker(db_session, "TSLA")
    base_date = date(2024, 2, 1)
    for offset, mentions in enumerate([50, 60, 70]):
        repo.upsert_summary(
            DailyTickerSummaryUpsertDTO(
                ticker="TSLA",
                summary_date=base_date + timedelta(days=offset),
                mention_count=mentions,
                engagement_count=mentions * 10,
            )
        )

    results = repo.get_summaries_for_ticker(
        "TSLA", start_date=base_date + timedelta(days=1)
    )

    assert [r.summary_date for r in results] == [
        base_date + timedelta(days=2),
        base_date + timedelta(days=1),
    ]

    limited = repo.get_summaries_for_ticker("TSLA", limit=1)
    assert len(limited) == 1
    assert limited[0].summary_date == base_date + timedelta(days=2)


def test_json_payload_round_trip(db_session, repo):
    """Ensure JSON and bullet list fields persist without mutation."""

    _ensure_ticker(db_session, "NVDA")
    article_ids = [111, 222]
    bullets = ["Bullish sentiment rising", "Institutional interest"]

    repo.upsert_summary(
        DailyTickerSummaryUpsertDTO(
            ticker="NVDA",
            summary_date=date(2024, 3, 5),
            mention_count=300,
            engagement_count=1200,
            top_articles=article_ids,
            llm_summary="NVIDIA remains a retail favourite.",
            llm_summary_bullets=bullets,
        )
    )

    fetched = repo.get_summaries_for_ticker("NVDA")
    assert fetched[0].top_articles == article_ids
    assert fetched[0].llm_summary_bullets == bullets


def test_cleanup_before_returns_deleted_count(db_session, repo):
    """Cleanup should remove records prior to the supplied date."""

    _ensure_ticker(db_session, "MSFT")
    repo.upsert_summary(
        DailyTickerSummaryUpsertDTO(
            ticker="MSFT",
            summary_date=date(2024, 1, 10),
            mention_count=10,
            engagement_count=20,
        )
    )
    repo.upsert_summary(
        DailyTickerSummaryUpsertDTO(
            ticker="MSFT",
            summary_date=date(2024, 1, 20),
            mention_count=15,
            engagement_count=25,
        )
    )

    deleted = repo.cleanup_before(date(2024, 1, 15))
    assert deleted == 1

    remaining = repo.get_summaries_for_ticker("MSFT")
    assert [r.summary_date for r in remaining] == [date(2024, 1, 20)]


def test_get_most_recent_summary_date_ignores_missing_content(db_session, repo):
    """Most recent summary date should consider only rows with LLM content."""

    _ensure_ticker(db_session, "AMD")
    empty_content_date = date(2024, 4, 1)
    recent_date = date(2024, 4, 2)

    repo.upsert_summary(
        DailyTickerSummaryUpsertDTO(
            ticker="AMD",
            summary_date=empty_content_date,
            mention_count=5,
            engagement_count=10,
            llm_summary=None,
        )
    )
    repo.upsert_summary(
        DailyTickerSummaryUpsertDTO(
            ticker="AMD",
            summary_date=recent_date,
            mention_count=25,
            engagement_count=50,
            llm_summary="Retail chatter increased.",
        )
    )

    assert repo.get_most_recent_summary_date() == recent_date


def test_llm_sentiment_enum_serialization(db_session, repo):
    """Test that LLM sentiment enum values are correctly serialized to database."""
    _ensure_ticker(db_session, "TSLA")

    # Test with enum object (should use value)
    dto_with_enum = DailyTickerSummaryUpsertDTO(
        ticker="TSLA",
        summary_date=date(2024, 1, 1),
        mention_count=100,
        engagement_count=500,
        llm_summary="Test summary",
        llm_sentiment=LLMSentimentCategory.BULLISH,  # Enum object
        llm_model="gpt-test",
    )

    created = repo.upsert_summary(dto_with_enum)
    assert created.llm_sentiment == LLMSentimentCategory.BULLISH

    # Verify the value was saved correctly (not the name)
    # Query directly from database to verify raw value
    from app.db.models import DailyTickerSummary

    entity = (
        db_session.query(DailyTickerSummary)
        .filter_by(ticker="TSLA", summary_date=date(2024, 1, 1))
        .first()
    )
    assert entity is not None
    # The enum value should be "Bullish", not "BULLISH"
    assert entity.llm_sentiment == LLMSentimentCategory.BULLISH
    assert entity.llm_sentiment.value == "Bullish"

    # Test with different enum values
    for sentiment_enum in [
        LLMSentimentCategory.BEARISH,
        LLMSentimentCategory.NEUTRAL,
        LLMSentimentCategory.TO_THE_MOON,
    ]:
        dto = DailyTickerSummaryUpsertDTO(
            ticker="TSLA",
            summary_date=date(2024, 1, 2),
            mention_count=100,
            engagement_count=500,
            llm_summary="Test summary",
            llm_sentiment=sentiment_enum,
            llm_model="gpt-test",
        )
        created = repo.upsert_summary(dto)
        assert created.llm_sentiment == sentiment_enum
        assert created.llm_sentiment.value in ["Bearish", "Neutral", "🚀 To the Moon"]
