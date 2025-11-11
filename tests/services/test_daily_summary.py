from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.config import settings
from app.db.models import Article, ArticleTicker, Ticker
from app.services.daily_summary import DailySummaryService


def _seed_daily_summary_data(db_session) -> None:
    tickers = [
        Ticker(symbol="TSLA", name="Tesla"),
        Ticker(symbol="AAPL", name="Apple"),
        Ticker(symbol="VOO", name="Vanguard S&P 500 ETF"),
    ]
    db_session.add_all(tickers)
    db_session.flush()

    articles = [
        Article(
            source="reddit",
            url="https://reddit.com/tsla-1",
            published_at=datetime(2024, 5, 2, 15, 0, tzinfo=UTC),
            title="TSLA beats delivery expectations",
            text="Tesla delivered a record number of vehicles this quarter, exceeding analyst expectations.",
            reddit_id="tsla1",
            subreddit="wallstreetbets",
            author="poster1",
            upvotes=420,
            num_comments=120,
            sentiment=0.45,
        ),
        Article(
            source="reddit",
            url="https://reddit.com/tsla-2",
            published_at=datetime(2024, 5, 2, 19, 30, tzinfo=UTC),
            title="Is Tesla undervalued right now?",
            text="Discussion about Tesla's current valuation and whether it's a good buy.",
            reddit_id="tsla2",
            subreddit="stocks",
            author="poster2",
            upvotes=80,
            num_comments=35,
            sentiment=-0.15,
        ),
        Article(
            source="reddit",
            url="https://reddit.com/aapl-1",
            published_at=datetime(2024, 5, 2, 16, 0, tzinfo=UTC),
            title="Apple announces new buyback",
            text="Apple announced a new share buyback program.",
            reddit_id="aapl1",
            subreddit="investing",
            author="poster3",
            upvotes=50,
            num_comments=15,
            sentiment=0.25,
        ),
        Article(
            source="reddit",
            url="https://reddit.com/voo-1",
            published_at=datetime(2024, 5, 2, 18, 0, tzinfo=UTC),
            title="ETF flow discussion",
            text="Discussion about ETF flows and market trends.",
            reddit_id="voo1",
            subreddit="investing",
            author="poster4",
            upvotes=12,
            num_comments=4,
            sentiment=0.1,
        ),
    ]
    db_session.add_all(articles)
    db_session.flush()

    links = [
        ArticleTicker(
            article_id=articles[0].id,
            ticker="TSLA",
            confidence=0.9,
            matched_terms=["tsla", "tesla"],
        ),
        ArticleTicker(
            article_id=articles[1].id,
            ticker="TSLA",
            confidence=0.8,
            matched_terms=["tsla"],
        ),
        ArticleTicker(
            article_id=articles[2].id,
            ticker="AAPL",
            confidence=0.95,
            matched_terms=["aapl", "apple"],
        ),
        ArticleTicker(
            article_id=articles[3].id,
            ticker="VOO",
            confidence=0.8,
            matched_terms=["voo"],
        ),
    ]
    db_session.add_all(links)
    db_session.commit()


def _build_summary(db_session, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "daily_summary_min_mentions", 2)
    monkeypatch.setattr(settings, "daily_summary_max_tickers", 5)
    monkeypatch.setattr(settings, "daily_summary_window_timezone", "America/New_York")
    monkeypatch.setattr(settings, "daily_summary_window_start_hour", 7)
    monkeypatch.setattr(settings, "daily_summary_window_end_hour", 19)

    service = DailySummaryService(db_session)
    # Mock datetime.now to avoid freezegun's module inspection issues with transformers
    # Set time to May 3rd 2:30 AM so "previous day" is May 2nd (when test data is from)
    from zoneinfo import ZoneInfo

    tz = ZoneInfo("America/New_York")
    target_time = datetime(2024, 5, 3, 2, 30, 0, tzinfo=tz)

    # Create a mock datetime module that preserves all datetime functionality except now()
    import app.services.daily_summary as daily_summary_module

    original_datetime = daily_summary_module.datetime

    class MockDatetime:
        @staticmethod
        def now(tz=None):
            return target_time if tz else target_time.astimezone(UTC)

        def __getattr__(self, name):
            return getattr(original_datetime, name)

    monkeypatch.setattr(daily_summary_module, "datetime", MockDatetime())

    summary = service.load_previous_day_summary()
    return service, summary


def test_load_previous_day_summary_filters_and_scores(db_session, monkeypatch):
    _seed_daily_summary_data(db_session)
    service, summary = _build_summary(db_session, monkeypatch)

    assert summary.window_start == datetime(2024, 5, 2, 11, 0, tzinfo=UTC)
    assert summary.window_end == datetime(2024, 5, 2, 23, 0, tzinfo=UTC)

    assert len(summary.tickers) == 1
    ticker_summary = summary.tickers[0]
    assert ticker_summary.ticker == "TSLA"
    assert ticker_summary.mentions == 2
    assert (
        ticker_summary.articles[0].engagement_score
        > ticker_summary.articles[1].engagement_score
    )


def test_build_payloads_include_api_key_and_prompt(db_session, monkeypatch):
    _seed_daily_summary_data(db_session)
    monkeypatch.setattr(settings, "openai_api_key", "sk-test")
    monkeypatch.setattr(settings, "daily_summary_llm_model", "gpt-test")

    service, summary = _build_summary(db_session, monkeypatch)

    langchain_payload = service.build_langchain_payload(summary)
    assert langchain_payload["llm"]["api_key"] == "sk-test"
    assert "TSLA" in langchain_payload["prompt"]
    assert langchain_payload["metadata"]["tickers"][0]["mentions"] == 2
    first_article = langchain_payload["metadata"]["tickers"][0]["articles"][0]
    assert first_article["matched_terms"] == ["tsla", "tesla"]
    assert first_article["sentiment"] == pytest.approx(0.45)
    assert first_article["subreddit"] == "wallstreetbets"


def test_langchain_payload_requires_api_key(db_session, monkeypatch):
    _seed_daily_summary_data(db_session)
    monkeypatch.setattr(settings, "openai_api_key", None)

    service, summary = _build_summary(db_session, monkeypatch)

    with pytest.raises(ValueError):
        service.build_langchain_payload(summary)


def test_generate_langchain_summary_invokes_model(db_session, monkeypatch):
    _seed_daily_summary_data(db_session)
    monkeypatch.setattr(settings, "openai_api_key", "sk-test")
    monkeypatch.setattr(settings, "daily_summary_llm_model", "gpt-test")
    monkeypatch.setattr(settings, "daily_summary_llm_temperature", 0.5)
    monkeypatch.setattr(settings, "daily_summary_llm_timeout_seconds", 45)
    monkeypatch.setattr(settings, "daily_summary_llm_max_tokens", 500)

    service, summary = _build_summary(db_session, monkeypatch)

    class FakeModel:
        def __init__(self) -> None:
            self.batch_inputs: list[str] = []

        def batch(self, prompts, config=None):
            self.batch_inputs.extend(prompts)
            return [type("Resp", (), {"content": "Daily summary"})()]

    fake_model = FakeModel()

    def _fake_init(model_name: str, **kwargs):
        assert model_name == "gpt-test"
        assert kwargs["temperature"] == 0.5
        assert kwargs["timeout"] == 45
        assert kwargs["max_tokens"] == 500
        assert kwargs["api_key"] == "sk-test"
        return fake_model

    monkeypatch.setattr("app.services.daily_summary.init_chat_model", _fake_init)

    responses = service.generate_langchain_summary(summary)
    # generate_langchain_summary uses build_prompt_for_ticker for each ticker
    expected_prompt = service.build_prompt_for_ticker(
        summary.tickers[0], summary.window_start, summary.window_end
    )
    assert fake_model.batch_inputs == [expected_prompt]
    assert responses == ["Daily summary"]
