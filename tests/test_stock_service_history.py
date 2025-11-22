"""Tests for StockDataService historical data features."""

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from app.db.models import StockPriceHistory
from app.services.stock_data import StockDataService


@pytest.fixture
def stock_service():
    """Create stock service instance."""
    return StockDataService()


@pytest.fixture
def mock_yfinance():
    """Mock yfinance ticker."""
    with patch("app.services.stock_data.yf.Ticker") as mock:
        yield mock


class TestStockDataServiceHistory:
    """Test historical data fetching and caching logic."""

    @pytest.mark.asyncio
    async def test_get_historical_data_range_success(
        self, stock_service, mock_yfinance
    ):
        """Test fetching historical data range successfully."""
        # Setup mock response
        mock_ticker = MagicMock()
        mock_yfinance.return_value = mock_ticker

        # Create sample DataFrame
        dates = pd.date_range(start="2024-01-01", periods=3, freq="h", tz="UTC")
        data = {
            "Open": [100.0, 101.0, 102.0],
            "High": [101.0, 102.0, 103.0],
            "Low": [99.0, 100.0, 101.0],
            "Close": [100.5, 101.5, 102.5],
            "Volume": [1000, 2000, 3000],
        }
        df = pd.DataFrame(data, index=dates)
        mock_ticker.history.return_value = df

        # Execute
        start = datetime(2024, 1, 1, tzinfo=UTC)
        end = datetime(2024, 1, 2, tzinfo=UTC)
        result = await stock_service.get_historical_data_range(
            "AAPL", start, end, interval="1h"
        )

        # Verify
        assert len(result) == 3
        assert result[0]["timestamp"] == dates[0]
        assert result[0]["close"] == 100.5
        assert result[0]["volume"] == 1000
        mock_ticker.history.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_historical_data_range_empty(self, stock_service, mock_yfinance):
        """Test fetching historical data with empty response."""
        mock_ticker = MagicMock()
        mock_yfinance.return_value = mock_ticker
        mock_ticker.history.return_value = pd.DataFrame()

        start = datetime(2024, 1, 1, tzinfo=UTC)
        end = datetime(2024, 1, 2, tzinfo=UTC)
        result = await stock_service.get_historical_data_range("AAPL", start, end)

        assert result == []

    @pytest.mark.asyncio
    async def test_get_price_history_full_db(
        self, stock_service, db_session, mock_yfinance
    ):
        """Test getting history when DB has full data (no fetch)."""
        # Insert recent data into DB
        now = datetime.now(UTC)
        dates = [now - timedelta(hours=i) for i in range(5)]

        for dt in dates:
            history = StockPriceHistory(
                symbol="AAPL", date=dt, close_price=150.0, volume=1000, created_at=now
            )
            db_session.add(history)
        db_session.commit()

        # Mock yfinance to ensure it's NOT called
        mock_ticker = MagicMock()
        mock_yfinance.return_value = mock_ticker

        # Execute
        result = await stock_service.get_price_history(db_session, "AAPL", days=1)

        # Verify
        assert len(result) == 5
        # yfinance should NOT be called because data is fresh (latest is 'now')
        mock_ticker.history.assert_not_called()

    @pytest.mark.asyncio
    async def test_get_price_history_partial_db(
        self, stock_service, db_session, mock_yfinance
    ):
        """Test getting history when DB has old data (fetch tail)."""
        # Insert old data into DB (older than 2 days)
        now = datetime.now(UTC)
        old_date = now - timedelta(days=3)

        history = StockPriceHistory(
            symbol="AAPL",
            date=old_date,
            close_price=140.0,
            volume=1000,
            created_at=old_date,
        )
        db_session.add(history)
        db_session.commit()

        # Mock yfinance response for missing range
        mock_ticker = MagicMock()
        mock_yfinance.return_value = mock_ticker

        # Return 1 new point
        new_date = now - timedelta(hours=1)
        dates = pd.date_range(start=new_date, periods=1, freq="h", tz="UTC")
        data = {
            "Open": [150.0],
            "High": [151.0],
            "Low": [149.0],
            "Close": [150.5],
            "Volume": [5000],
        }
        df = pd.DataFrame(data, index=dates)
        mock_ticker.history.return_value = df

        # Execute
        result = await stock_service.get_price_history(db_session, "AAPL", days=5)

        # Verify result contains both old and new
        assert len(result) == 2

        # Verify timestamps (ignoring timezone string differences due to SQLite)
        # result[0] is new (from API->DB), result[1] is old (from DB)
        res_ts_0 = datetime.fromisoformat(result[0]["timestamp"]).replace(tzinfo=None)
        exp_ts_0 = dates[0].to_pydatetime().replace(tzinfo=None)
        assert res_ts_0 == exp_ts_0

        res_ts_1 = datetime.fromisoformat(result[1]["timestamp"]).replace(tzinfo=None)
        exp_ts_1 = old_date.replace(tzinfo=None)
        # Allow small difference due to float/microsecond precision
        assert abs((res_ts_1 - exp_ts_1).total_seconds()) < 1

        # Verify yfinance called
        mock_ticker.history.assert_called_once()

        # Verify DB updated
        saved_rows = db_session.query(StockPriceHistory).filter_by(symbol="AAPL").all()
        assert len(saved_rows) == 2

    @pytest.mark.asyncio
    async def test_get_price_history_empty_db(
        self, stock_service, db_session, mock_yfinance
    ):
        """Test getting history when DB is empty (full fetch)."""
        # Mock yfinance response
        mock_ticker = MagicMock()
        mock_yfinance.return_value = mock_ticker

        # Use recent dates so they fall within the query window
        now = datetime.now(UTC)
        start_date = now - timedelta(days=1)
        dates = pd.date_range(start=start_date, periods=3, freq="h", tz="UTC")

        data = {
            "Open": [100.0] * 3,
            "High": [100.0] * 3,
            "Low": [100.0] * 3,
            "Close": [100.0] * 3,
            "Volume": [1000] * 3,
        }
        df = pd.DataFrame(data, index=dates)
        mock_ticker.history.return_value = df

        # Execute
        result = await stock_service.get_price_history(db_session, "AAPL", days=30)

        # Verify
        assert len(result) == 3
        mock_ticker.history.assert_called_once()

        # Verify DB populated
        count = db_session.query(StockPriceHistory).count()
        assert count == 3
