"""Tests for stock data service."""

import asyncio
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from app.services.stock_data import StockDataService


@pytest.fixture
def stock_service():
    """Create a stock data service instance."""
    return StockDataService()


@pytest.fixture
def mock_yfinance_ticker():
    """Create a mock yfinance Ticker object."""
    mock_ticker = MagicMock()

    # Mock info data
    mock_ticker.info = {
        "currentPrice": 150.25,
        "previousClose": 148.50,
        "marketState": "REGULAR",
        "exchange": "NASDAQ",
        "currency": "USD",
    }

    # Mock historical data
    mock_hist = pd.DataFrame(
        {
            "Open": [148.0, 149.0, 150.0],
            "High": [149.5, 150.5, 151.0],
            "Low": [147.5, 148.5, 149.5],
            "Close": [148.5, 149.5, 150.5],
            "Volume": [1000000, 1100000, 1200000],
        },
        index=pd.date_range("2025-01-01", periods=3, freq="D"),
    )

    mock_ticker.history = MagicMock(return_value=mock_hist)

    return mock_ticker


class TestStockDataService:
    """Test suite for StockDataService."""

    def test_normalize_symbol(self, stock_service):
        """Test symbol normalization."""
        assert stock_service._normalize_symbol("BRK.B") == "BRK-B"
        assert stock_service._normalize_symbol("BRK.A") == "BRK-A"
        assert stock_service._normalize_symbol("AAPL") == "AAPL"
        assert stock_service._normalize_symbol("aapl") == "AAPL"

    @pytest.mark.asyncio
    async def test_rate_limit(self, stock_service):
        """Test rate limiting functionality."""
        start_time = asyncio.get_event_loop().time()

        # First call should be immediate
        await stock_service._rate_limit()

        # Second call should wait
        await stock_service._rate_limit()

        elapsed = asyncio.get_event_loop().time() - start_time

        # Should have waited at least min_request_interval
        assert elapsed >= stock_service._min_request_interval

    @pytest.mark.asyncio
    async def test_get_stock_price_success(self, stock_service, mock_yfinance_ticker):
        """Test successful stock price fetch."""
        with patch(
            "app.services.stock_data.yf.Ticker", return_value=mock_yfinance_ticker
        ):
            result = await stock_service.get_stock_price("AAPL")

            assert result is not None
            assert result["symbol"] == "AAPL"
            assert result["price"] == 150.25
            assert result["previous_close"] == 148.50
            assert result["change"] == 1.75
            assert abs(result["change_percent"] - 1.18) < 0.01
            assert result["currency"] == "USD"
            assert result["exchange"] == "NASDAQ"
            assert result["market_state"] == "REGULAR"

    @pytest.mark.asyncio
    async def test_get_stock_price_with_fast_info_fallback(self, stock_service):
        """Test stock price fetch with fast_info fallback."""
        mock_ticker = MagicMock()
        mock_ticker.info = {}  # Empty info

        # Mock fast_info properly
        mock_fast_info = {
            "lastPrice": 150.25,
            "previousClose": 148.50,
        }
        mock_ticker.fast_info = mock_fast_info

        with patch("app.services.stock_data.yf.Ticker", return_value=mock_ticker):
            result = await stock_service.get_stock_price("AAPL")

            assert result is not None
            assert result["price"] == 150.25
            assert result["previous_close"] == 148.50

    @pytest.mark.asyncio
    async def test_get_stock_price_no_data(self, stock_service):
        """Test stock price fetch when no data available."""
        mock_ticker = MagicMock()
        mock_ticker.info = {}

        # Mock fast_info with no data
        mock_fast_info = MagicMock()
        mock_fast_info.__getitem__ = MagicMock(side_effect=KeyError)
        mock_fast_info.get = MagicMock(return_value=None)
        mock_ticker.fast_info = mock_fast_info

        with patch("app.services.stock_data.yf.Ticker", return_value=mock_ticker):
            result = await stock_service.get_stock_price("INVALID")

            assert result is None

    @pytest.mark.asyncio
    async def test_get_stock_price_with_retry(self, stock_service):
        """Test stock price fetch with retry on failure."""
        # First two calls fail, third succeeds
        call_count = 0

        def mock_ticker_factory(symbol):
            nonlocal call_count
            call_count += 1

            mock_ticker = MagicMock()
            if call_count < 3:
                # First two attempts fail
                mock_ticker.info = {}
                mock_ticker.fast_info = {}
            else:
                # Third attempt succeeds
                mock_ticker.info = {
                    "currentPrice": 150.25,
                    "previousClose": 148.50,
                    "marketState": "REGULAR",
                    "exchange": "NASDAQ",
                    "currency": "USD",
                }
            return mock_ticker

        with patch(
            "app.services.stock_data.yf.Ticker", side_effect=mock_ticker_factory
        ):
            # Should succeed on third attempt
            result = await stock_service.get_stock_price("AAPL")

            assert result is not None
            assert call_count == 3

    @pytest.mark.asyncio
    async def test_get_stock_price_max_retries_exceeded(self, stock_service):
        """Test stock price fetch when max retries exceeded."""
        mock_ticker = MagicMock()
        mock_ticker.info = property(
            lambda self: (_ for _ in ()).throw(Exception("API error"))
        )

        with patch("app.services.stock_data.yf.Ticker", return_value=mock_ticker):
            result = await stock_service.get_stock_price("AAPL")

            assert result is None

    @pytest.mark.asyncio
    async def test_get_historical_data_success(
        self, stock_service, mock_yfinance_ticker
    ):
        """Test successful historical data fetch."""
        with patch(
            "app.services.stock_data.yf.Ticker", return_value=mock_yfinance_ticker
        ):
            result = await stock_service.get_historical_data("AAPL", "1mo")

            assert result is not None
            assert result["symbol"] == "AAPL"
            assert result["period"] == "1mo"
            assert result["meta"]["source"] == "yahoo"
            assert len(result["data"]) == 3

            # Check first data point
            first_point = result["data"][0]
            assert "date" in first_point
            assert "open" in first_point
            assert "high" in first_point
            assert "low" in first_point
            assert "close" in first_point
            assert "price" in first_point
            assert "volume" in first_point
            assert first_point["close"] == 148.5

    @pytest.mark.asyncio
    async def test_get_historical_data_empty_result(self, stock_service):
        """Test historical data fetch with empty result."""
        mock_ticker = MagicMock()
        mock_ticker.history = MagicMock(return_value=pd.DataFrame())

        with patch("app.services.stock_data.yf.Ticker", return_value=mock_ticker):
            result = await stock_service.get_historical_data("INVALID", "1mo")

            assert result is None

    @pytest.mark.asyncio
    async def test_get_historical_data_different_periods(
        self, stock_service, mock_yfinance_ticker
    ):
        """Test historical data fetch with different periods."""
        periods = ["1d", "5d", "1mo", "3mo", "6mo", "1y", "2y", "5y"]

        with patch(
            "app.services.stock_data.yf.Ticker", return_value=mock_yfinance_ticker
        ):
            for period in periods:
                result = await stock_service.get_historical_data("AAPL", period)

                assert result is not None
                assert result["period"] == period

    @pytest.mark.asyncio
    async def test_get_multiple_prices(self, stock_service, mock_yfinance_ticker):
        """Test fetching multiple stock prices."""
        with patch(
            "app.services.stock_data.yf.Ticker", return_value=mock_yfinance_ticker
        ):
            symbols = ["AAPL", "MSFT", "GOOGL"]
            results = await stock_service.get_multiple_prices(symbols)

            assert len(results) == 3
            assert all(symbol in results for symbol in symbols)
            assert all(results[symbol] is not None for symbol in symbols)

    @pytest.mark.asyncio
    async def test_get_multiple_prices_with_failures(self, stock_service):
        """Test fetching multiple stock prices with some failures."""

        def mock_ticker_factory(symbol):
            mock_ticker = MagicMock()
            if symbol == "INVALID":
                mock_ticker.info = {}
                mock_fast_info = MagicMock()
                mock_fast_info.get = MagicMock(return_value=None)
                mock_ticker.fast_info = mock_fast_info
            else:
                mock_ticker.info = {
                    "currentPrice": 150.25,
                    "previousClose": 148.50,
                    "marketState": "REGULAR",
                    "exchange": "NASDAQ",
                    "currency": "USD",
                }
            return mock_ticker

        with patch(
            "app.services.stock_data.yf.Ticker", side_effect=mock_ticker_factory
        ):
            symbols = ["AAPL", "INVALID", "MSFT"]
            results = await stock_service.get_multiple_prices(symbols)

            assert len(results) == 3
            assert results["AAPL"] is not None
            assert results["INVALID"] is None
            assert results["MSFT"] is not None

    @pytest.mark.asyncio
    async def test_symbol_normalization_in_fetch(
        self, stock_service, mock_yfinance_ticker
    ):
        """Test that symbols are normalized before fetching."""
        with patch(
            "app.services.stock_data.yf.Ticker", return_value=mock_yfinance_ticker
        ) as mock_yf:
            await stock_service.get_stock_price("BRK.B")

            # Should be called with normalized symbol
            mock_yf.assert_called_with("BRK-B")
