"""Tests for canonical ticker merge script."""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import (
    Article,
    ArticleTicker,
    Base,
    DailyTickerSummary,
    LLMSentimentCategory,
    StockPrice,
    StockPriceHistory,
    Ticker,
    User,
    UserTickerFollow,
)
from app.scripts.merge_ticker_aliases import TickerMergeService


def _create_session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    return SessionLocal()


def test_merge_aliases_moves_all_rows_to_canonical_symbol() -> None:
    session = _create_session()
    try:
        goog = Ticker(
            symbol="GOOG",
            name="Alphabet Class C",
            aliases=[],
            exchange="NMS",
            sources=["news"],
            is_sp500=True,
        )
        googl = Ticker(
            symbol="GOOGL",
            name="Alphabet Class A",
            aliases=["Alphabet Inc"],
            exchange="NMS",
            sources=["reddit"],
            is_sp500=True,
        )
        session.add_all([goog, googl])

        article_one = Article(
            source="news",
            url="https://example.com/a",
            title="Alphabet beats",
            published_at=datetime(2024, 1, 1, tzinfo=UTC),
        )
        article_two = Article(
            source="news",
            url="https://example.com/b",
            title="Alphabet guidance",
            published_at=datetime(2024, 1, 2, tzinfo=UTC),
        )
        session.add_all([article_one, article_two])
        session.flush()

        session.add_all(
            [
                ArticleTicker(article_id=article_one.id, ticker="GOOG", confidence=0.9),
                ArticleTicker(
                    article_id=article_one.id, ticker="GOOGL", confidence=0.9
                ),
                ArticleTicker(
                    article_id=article_two.id, ticker="GOOGL", confidence=0.9
                ),
            ]
        )

        session.add_all(
            [
                DailyTickerSummary(
                    ticker="GOOG",
                    summary_date=date(2024, 1, 1),
                    mention_count=5,
                    engagement_count=10,
                    avg_sentiment=0.4,
                    sentiment_stddev=0.1,
                    sentiment_min=-0.2,
                    sentiment_max=0.6,
                    top_articles=[article_one.id],
                    llm_summary="GOOG summary",
                    llm_summary_bullets=["one"],
                    llm_sentiment=LLMSentimentCategory.BULLISH,
                    llm_model="model-a",
                    llm_version="v1",
                ),
                DailyTickerSummary(
                    ticker="GOOGL",
                    summary_date=date(2024, 1, 1),
                    mention_count=7,
                    engagement_count=20,
                    avg_sentiment=0.1,
                    sentiment_stddev=0.05,
                    sentiment_min=-0.5,
                    sentiment_max=0.7,
                    top_articles=[article_two.id],
                ),
            ]
        )

        session.add_all(
            [
                StockPrice(
                    symbol="GOOG",
                    price=100.0,
                    previous_close=None,
                    change=0.5,
                    change_percent=0.1,
                    open=99.0,
                    day_high=101.0,
                    day_low=98.0,
                    volume=1_000,
                    bid=99.5,
                    ask=100.5,
                    bid_size=10,
                    ask_size=12,
                    market_cap=1_000_000,
                    shares_outstanding=100_000,
                    average_volume=900,
                    average_volume_10d=800,
                    market_state="CLOSED",
                    currency="USD",
                    exchange="NMS",
                ),
                StockPrice(
                    symbol="GOOGL",
                    price=120.0,
                    previous_close=110.0,
                    change=0.7,
                    change_percent=0.2,
                    open=118.0,
                    day_high=121.0,
                    day_low=117.0,
                    volume=1_500,
                    bid=119.5,
                    ask=120.5,
                    bid_size=14,
                    ask_size=15,
                    market_cap=1_100_000,
                    shares_outstanding=110_000,
                    average_volume=950,
                    average_volume_10d=820,
                    market_state="CLOSED",
                    currency="USD",
                    exchange="NMS",
                ),
            ]
        )

        session.add_all(
            [
                StockPriceHistory(
                    symbol="GOOG",
                    date=datetime(2024, 1, 1, tzinfo=UTC),
                    open_price=99.0,
                    high_price=101.0,
                    low_price=98.0,
                    close_price=100.0,
                    volume=1_000,
                ),
                StockPriceHistory(
                    symbol="GOOGL",
                    date=datetime(2024, 1, 2, tzinfo=UTC),
                    open_price=118.0,
                    high_price=121.0,
                    low_price=117.0,
                    close_price=120.0,
                    volume=1_500,
                ),
            ]
        )

        user = User(email="user@example.com")
        session.add(user)
        session.flush()

        session.add_all(
            [
                UserTickerFollow(user_id=user.id, ticker="GOOG"),
                UserTickerFollow(user_id=user.id, ticker="GOOGL"),
            ]
        )

        session.commit()

        service = TickerMergeService(session)
        results = service.merge_all()

        assert "GOOGL->GOOG" in results
        assert session.query(Ticker).filter_by(symbol="GOOGL").count() == 0

        merged_ticker = session.query(Ticker).filter_by(symbol="GOOG").one()
        assert "GOOGL" in merged_ticker.aliases
        assert merged_ticker.sources.count("news") == 1
        assert "reddit" in merged_ticker.sources

        article_links = session.query(ArticleTicker).filter_by(ticker="GOOG").all()
        assert len(article_links) == 2
        assert all(link.ticker == "GOOG" for link in article_links)

        summary = (
            session.query(DailyTickerSummary)
            .filter_by(ticker="GOOG", summary_date=date(2024, 1, 1))
            .one()
        )
        assert summary.mention_count == 12
        assert summary.engagement_count == 30
        assert summary.sentiment_min == -0.5
        assert summary.sentiment_max == 0.7
        assert summary.avg_sentiment == pytest.approx(0.225, rel=1e-5)
        assert summary.top_articles == [article_one.id, article_two.id]
        assert summary.llm_summary == "GOOG summary"
        assert summary.llm_summary_bullets == ["one"]

        stock_price = session.query(StockPrice).filter_by(symbol="GOOG").one()
        assert stock_price.previous_close == 110.0
        assert stock_price.price == 100.0
        assert session.query(StockPrice).filter_by(symbol="GOOGL").count() == 0

        history_rows = session.query(StockPriceHistory).filter_by(symbol="GOOG").all()
        assert len(history_rows) == 2

        follows = session.query(UserTickerFollow).filter_by(ticker="GOOG").all()
        assert len(follows) == 1
    finally:
        session.close()
