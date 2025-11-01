"""Tests for on-demand stock price caching helpers."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest

from app.db.models import StockPrice
from app.services.stock_price_cache import ensure_fresh_stock_price


@pytest.mark.asyncio
async def test_ensure_fresh_stock_price_creates_record(db_session, monkeypatch):
    """Ensure helper fetches and persists data when no record exists."""
    mock_data = {
        "symbol": "AAPL",
        "price": 150.25,
        "previous_close": 149.5,
        "change": 0.75,
        "change_percent": 0.5,
        "market_state": "OPEN",
        "currency": "USD",
        "exchange": "NASDAQ",
        "open": 149.8,
        "day_high": 151.0,
        "day_low": 148.9,
        "volume": 1000000,
    }

    mock_fetch = AsyncMock(return_value=mock_data)
    monkeypatch.setattr(
        "app.services.stock_price_cache.stock_service.get_stock_price",
        mock_fetch,
    )

    result = await ensure_fresh_stock_price(db_session, "AAPL")

    assert result is not None
    assert result.symbol == "AAPL"
    assert result.price == mock_data["price"]
    assert mock_fetch.await_count == 1

    # Verify record persisted
    saved = db_session.query(StockPrice).filter_by(symbol="AAPL").first()
    assert saved is not None
    assert saved.price == mock_data["price"]


@pytest.mark.asyncio
async def test_ensure_fresh_stock_price_skips_when_recent(db_session, monkeypatch):
    """Existing fresh data should bypass the external fetch."""
    now = datetime.now(UTC)
    fresh_record = StockPrice(
        symbol="MSFT",
        price=300.0,
        previous_close=295.0,
        change=5.0,
        change_percent=1.69,
        updated_at=now,
    )
    db_session.add(fresh_record)
    db_session.commit()

    mock_fetch = AsyncMock(return_value=None)
    monkeypatch.setattr(
        "app.services.stock_price_cache.stock_service.get_stock_price",
        mock_fetch,
    )

    result = await ensure_fresh_stock_price(db_session, "MSFT")

    assert result is not None
    assert result.price == 300.0
    mock_fetch.assert_not_called()


@pytest.mark.asyncio
async def test_ensure_fresh_stock_price_refreshes_when_stale(db_session, monkeypatch):
    """Stale records should trigger a refresh fetch."""
    stale_record = StockPrice(
        symbol="TSLA",
        price=200.0,
        previous_close=198.0,
        change=2.0,
        change_percent=1.01,
        updated_at=datetime.now(UTC) - timedelta(hours=2),
    )
    db_session.add(stale_record)
    db_session.commit()

    mock_data = {
        "symbol": "TSLA",
        "price": 210.0,
        "previous_close": 205.0,
        "change": 5.0,
        "change_percent": 2.44,
        "market_state": "OPEN",
        "currency": "USD",
    }

    mock_fetch = AsyncMock(return_value=mock_data)
    monkeypatch.setattr(
        "app.services.stock_price_cache.stock_service.get_stock_price",
        mock_fetch,
    )

    result = await ensure_fresh_stock_price(db_session, "tsla")

    assert result is not None
    assert result.price == 210.0
    assert mock_fetch.await_count == 1

    updated = db_session.query(StockPrice).filter_by(symbol="TSLA").first()
    assert updated.price == 210.0
