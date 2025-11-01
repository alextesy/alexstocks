from fastapi.testclient import TestClient

from app.config import settings
from app.main import app

client = TestClient(app)


def test_time_series_days_capped():
    # days greater than cap should be rejected by validation (422) due to Query(le=MAX)
    resp = client.get(
        "/api/sentiment/time-series",
        params={"ticker": "AAPL", "days": settings.MAX_DAYS_TIME_SERIES + 1},
    )
    assert resp.status_code in (422, 429)  # may be 429 if RL kicks in during CI


def test_mentions_hours_capped():
    resp = client.get(
        "/api/mentions/hourly",
        params={"tickers": "AAPL,TSLA", "hours": settings.MAX_HOURS_MENTIONS + 1},
    )
    assert resp.status_code in (422, 429)


def test_ticker_articles_limit_capped_validation():
    resp = client.get(
        "/api/ticker/TSLA/articles",
        params={"page": 1, "limit": settings.MAX_LIMIT_ARTICLES + 1},
    )
    assert resp.status_code in (422, 429)
