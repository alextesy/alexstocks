"""Unit tests for stock price service."""

import math
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.db.models import StockPrice
from app.services.stock_price_service import (
    PRICE_FRESHNESS_THRESHOLD_MINUTES,
    StockPriceService,
)


@pytest.fixture
def stock_price_service():
    """Create a StockPriceService instance."""
    return StockPriceService()


@pytest.fixture
def mock_db():
    """Create a mock database session."""
    return MagicMock()


class TestValidatePriceData:
    """Tests for price data validation."""

    def test_validate_price_data_valid(self, stock_price_service):
        """Test validation with valid price data."""
        data = {
            "symbol": "AAPL",
            "price": 150.50,
            "previous_close": 148.25,
            "change": 2.25,
            "change_percent": 1.52,
        }
        assert stock_price_service.validate_price_data(data) is True

    def test_validate_price_data_none_data(self, stock_price_service):
        """Test validation with None data."""
        assert stock_price_service.validate_price_data(None) is False

    def test_validate_price_data_none_price(self, stock_price_service):
        """Test validation with None price."""
        data = {"symbol": "AAPL", "price": None}
        assert stock_price_service.validate_price_data(data) is False

    def test_validate_price_data_nan_price(self, stock_price_service):
        """Test validation with NaN price."""
        data = {"symbol": "AAPL", "price": math.nan}
        assert stock_price_service.validate_price_data(data) is False

    def test_validate_price_data_zero_price(self, stock_price_service):
        """Test validation with zero price."""
        data = {"symbol": "AAPL", "price": 0.0}
        assert stock_price_service.validate_price_data(data) is False

    def test_validate_price_data_negative_price(self, stock_price_service):
        """Test validation with negative price."""
        data = {"symbol": "AAPL", "price": -10.0}
        assert stock_price_service.validate_price_data(data) is False

    def test_validate_price_data_unrealistic_high_price(self, stock_price_service):
        """Test validation with unrealistically high price."""
        data = {"symbol": "AAPL", "price": 2000000.0}
        assert stock_price_service.validate_price_data(data) is False

    def test_validate_price_data_edge_case_penny_stock(self, stock_price_service):
        """Test validation with penny stock price."""
        data = {"symbol": "PENNY", "price": 0.01}
        assert stock_price_service.validate_price_data(data) is True

    def test_validate_price_data_edge_case_high_price(self, stock_price_service):
        """Test validation with high but realistic price."""
        data = {"symbol": "BRK.A", "price": 500000.0}
        assert stock_price_service.validate_price_data(data) is True


class TestIsPriceStale:
    """Tests for staleness checking."""

    def test_is_price_stale_none(self, stock_price_service):
        """Test staleness check with None."""
        assert stock_price_service.is_price_stale(None) is True

    def test_is_price_stale_no_timestamp(self, stock_price_service):
        """Test staleness check with missing timestamp."""
        stock_price = MagicMock(spec=StockPrice)
        stock_price.updated_at = None
        assert stock_price_service.is_price_stale(stock_price) is True

    def test_is_price_stale_fresh(self, stock_price_service):
        """Test staleness check with fresh data."""
        stock_price = MagicMock(spec=StockPrice)
        stock_price.updated_at = datetime.now(UTC) - timedelta(minutes=10)
        assert stock_price_service.is_price_stale(stock_price) is False

    def test_is_price_stale_exactly_threshold(self, stock_price_service):
        """Test staleness check at exact threshold."""
        stock_price = MagicMock(spec=StockPrice)
        stock_price.updated_at = datetime.now(UTC) - timedelta(
            minutes=PRICE_FRESHNESS_THRESHOLD_MINUTES
        )
        # At exactly 30 minutes, it should be stale (> threshold)
        assert stock_price_service.is_price_stale(stock_price) is True

    def test_is_price_stale_old(self, stock_price_service):
        """Test staleness check with old data."""
        stock_price = MagicMock(spec=StockPrice)
        stock_price.updated_at = datetime.now(UTC) - timedelta(hours=2)
        assert stock_price_service.is_price_stale(stock_price) is True

    def test_is_price_stale_just_before_threshold(self, stock_price_service):
        """Test staleness check just before threshold."""
        stock_price = MagicMock(spec=StockPrice)
        stock_price.updated_at = datetime.now(UTC) - timedelta(
            minutes=PRICE_FRESHNESS_THRESHOLD_MINUTES - 1
        )
        assert stock_price_service.is_price_stale(stock_price) is False


class TestGetOrRefreshPrice:
    """Tests for get_or_refresh_price method."""

    @pytest.mark.asyncio
    async def test_get_or_refresh_price_cache_hit_fresh(
        self, stock_price_service, mock_db
    ):
        """Test cache hit with fresh data."""
        # Setup mock cached price
        cached_price = MagicMock(spec=StockPrice)
        cached_price.symbol = "AAPL"
        cached_price.price = 150.0
        cached_price.previous_close = 148.0
        cached_price.change = 2.0
        cached_price.change_percent = 1.35
        cached_price.market_state = "OPEN"
        cached_price.currency = "USD"
        cached_price.exchange = "NASDAQ"
        cached_price.updated_at = datetime.now(UTC) - timedelta(minutes=10)

        mock_db.query.return_value.filter.return_value.first.return_value = cached_price

        result = await stock_price_service.get_or_refresh_price(mock_db, "AAPL")

        assert result is not None
        assert result["symbol"] == "AAPL"
        assert result["price"] == 150.0
        # Verify no API call was made (mock_db was not committed)
        assert not mock_db.commit.called

    @pytest.mark.asyncio
    async def test_get_or_refresh_price_cache_miss(self, stock_price_service, mock_db):
        """Test cache miss, fetch from API."""
        # No cached price
        mock_db.query.return_value.filter.return_value.first.return_value = None

        # Mock API response
        api_data = {
            "symbol": "AAPL",
            "price": 150.0,
            "previous_close": 148.0,
            "change": 2.0,
            "change_percent": 1.35,
            "market_state": "OPEN",
            "currency": "USD",
            "exchange": "NASDAQ",
        }

        with patch.object(
            stock_price_service.stock_data_service,
            "get_stock_price",
            new=AsyncMock(return_value=api_data),
        ):
            result = await stock_price_service.get_or_refresh_price(mock_db, "AAPL")

        assert result is not None
        assert result["symbol"] == "AAPL"
        assert result["price"] == 150.0
        # Verify database was updated
        assert mock_db.add.called
        assert mock_db.commit.called

    @pytest.mark.asyncio
    async def test_get_or_refresh_price_stale_data(self, stock_price_service, mock_db):
        """Test refresh when cached data is stale."""
        # Setup stale cached price
        cached_price = MagicMock(spec=StockPrice)
        cached_price.symbol = "AAPL"
        cached_price.price = 148.0
        cached_price.updated_at = datetime.now(UTC) - timedelta(hours=1)

        mock_db.query.return_value.filter.return_value.first.return_value = cached_price

        # Mock API response
        api_data = {
            "symbol": "AAPL",
            "price": 150.0,
            "previous_close": 148.0,
            "change": 2.0,
            "change_percent": 1.35,
            "market_state": "OPEN",
            "currency": "USD",
            "exchange": "NASDAQ",
        }

        with patch.object(
            stock_price_service.stock_data_service,
            "get_stock_price",
            new=AsyncMock(return_value=api_data),
        ):
            result = await stock_price_service.get_or_refresh_price(mock_db, "AAPL")

        assert result is not None
        assert result["price"] == 150.0
        # Verify database was updated
        assert mock_db.commit.called

    @pytest.mark.asyncio
    async def test_get_or_refresh_price_force_refresh(
        self, stock_price_service, mock_db
    ):
        """Test force refresh even with fresh data."""
        # Setup fresh cached price
        cached_price = MagicMock(spec=StockPrice)
        cached_price.symbol = "AAPL"
        cached_price.price = 148.0
        cached_price.updated_at = datetime.now(UTC) - timedelta(minutes=5)

        mock_db.query.return_value.filter.return_value.first.return_value = cached_price

        # Mock API response
        api_data = {
            "symbol": "AAPL",
            "price": 150.0,
            "previous_close": 148.0,
            "change": 2.0,
            "change_percent": 1.35,
            "market_state": "OPEN",
            "currency": "USD",
            "exchange": "NASDAQ",
        }

        with patch.object(
            stock_price_service.stock_data_service,
            "get_stock_price",
            new=AsyncMock(return_value=api_data),
        ):
            result = await stock_price_service.get_or_refresh_price(
                mock_db, "AAPL", force_refresh=True
            )

        assert result is not None
        assert result["price"] == 150.0
        assert mock_db.commit.called

    @pytest.mark.asyncio
    async def test_get_or_refresh_price_invalid_api_data(
        self, stock_price_service, mock_db
    ):
        """Test handling of invalid API data, fallback to stale cache."""
        # Setup stale cached price
        cached_price = MagicMock(spec=StockPrice)
        cached_price.symbol = "AAPL"
        cached_price.price = 148.0
        cached_price.previous_close = 147.0
        cached_price.change = 1.0
        cached_price.change_percent = 0.68
        cached_price.market_state = "CLOSED"
        cached_price.currency = "USD"
        cached_price.exchange = "NASDAQ"
        cached_price.updated_at = datetime.now(UTC) - timedelta(hours=1)

        mock_db.query.return_value.filter.return_value.first.return_value = cached_price

        # Mock invalid API response (zero price)
        api_data = {"symbol": "AAPL", "price": 0.0}

        with patch.object(
            stock_price_service.stock_data_service,
            "get_stock_price",
            new=AsyncMock(return_value=api_data),
        ):
            result = await stock_price_service.get_or_refresh_price(mock_db, "AAPL")

        # Should return stale cached data
        assert result is not None
        assert result["price"] == 148.0

    @pytest.mark.asyncio
    async def test_get_or_refresh_price_no_data_available(
        self, stock_price_service, mock_db
    ):
        """Test when no data is available (no cache, no API)."""
        # No cached price
        mock_db.query.return_value.filter.return_value.first.return_value = None

        # Mock no API response
        with patch.object(
            stock_price_service.stock_data_service,
            "get_stock_price",
            new=AsyncMock(return_value=None),
        ):
            result = await stock_price_service.get_or_refresh_price(mock_db, "INVALID")

        assert result is None


class TestGetTopNTickers:
    """Tests for getting top N tickers."""

    def test_get_top_n_tickers(self, stock_price_service, mock_db):
        """Test getting top N tickers."""
        # Mock query results
        mock_results = [
            ("AAPL", 100),
            ("TSLA", 90),
            ("NVDA", 80),
            ("MSFT", 70),
            ("AMZN", 60),
        ]

        mock_query = MagicMock()
        mock_query.join.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.group_by.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.all.return_value = mock_results

        mock_db.query.return_value = mock_query

        result = stock_price_service.get_top_n_tickers(mock_db, n=5)

        assert result == ["AAPL", "TSLA", "NVDA", "MSFT", "AMZN"]
        assert len(result) == 5

    def test_get_top_n_tickers_empty(self, stock_price_service, mock_db):
        """Test getting top N tickers with no data."""
        mock_query = MagicMock()
        mock_query.join.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.group_by.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.all.return_value = []

        mock_db.query.return_value = mock_query

        result = stock_price_service.get_top_n_tickers(mock_db, n=5)

        assert result == []


class TestRefreshTopNPrices:
    """Tests for refreshing top N prices."""

    @pytest.mark.asyncio
    async def test_refresh_top_n_prices_success(self, stock_price_service, mock_db):
        """Test successful refresh of top N prices."""
        # Mock get_top_n_tickers
        with patch.object(
            stock_price_service,
            "get_top_n_tickers",
            return_value=["AAPL", "TSLA", "NVDA"],
        ):
            # Mock API responses
            api_results = {
                "AAPL": {
                    "symbol": "AAPL",
                    "price": 150.0,
                    "previous_close": 148.0,
                    "change": 2.0,
                    "change_percent": 1.35,
                    "market_state": "OPEN",
                    "currency": "USD",
                    "exchange": "NASDAQ",
                },
                "TSLA": {
                    "symbol": "TSLA",
                    "price": 250.0,
                    "previous_close": 245.0,
                    "change": 5.0,
                    "change_percent": 2.04,
                    "market_state": "OPEN",
                    "currency": "USD",
                    "exchange": "NASDAQ",
                },
                "NVDA": {
                    "symbol": "NVDA",
                    "price": 800.0,
                    "previous_close": 790.0,
                    "change": 10.0,
                    "change_percent": 1.27,
                    "market_state": "OPEN",
                    "currency": "USD",
                    "exchange": "NASDAQ",
                },
            }

            with patch.object(
                stock_price_service.stock_data_service,
                "get_multiple_prices",
                new=AsyncMock(return_value=api_results),
            ):
                # Mock database query
                mock_db.query.return_value.filter.return_value.first.return_value = None

                result = await stock_price_service.refresh_top_n_prices(mock_db, n=3)

        assert result["requested"] == 3
        assert result["success"] == 3
        assert result["failed"] == 0
        assert len(result["errors"]) == 0

    @pytest.mark.asyncio
    async def test_refresh_top_n_prices_no_tickers(self, stock_price_service, mock_db):
        """Test refresh with no tickers available."""
        with patch.object(stock_price_service, "get_top_n_tickers", return_value=[]):
            result = await stock_price_service.refresh_top_n_prices(mock_db, n=50)

        assert result["requested"] == 0
        assert result["success"] == 0
        assert result["failed"] == 0

    @pytest.mark.asyncio
    async def test_refresh_top_n_prices_partial_failure(
        self, stock_price_service, mock_db
    ):
        """Test refresh with some failures."""
        with patch.object(
            stock_price_service, "get_top_n_tickers", return_value=["AAPL", "INVALID"]
        ):
            api_results = {
                "AAPL": {
                    "symbol": "AAPL",
                    "price": 150.0,
                    "previous_close": 148.0,
                    "change": 2.0,
                    "change_percent": 1.35,
                    "market_state": "OPEN",
                    "currency": "USD",
                    "exchange": "NASDAQ",
                },
                "INVALID": None,  # Failed to fetch
            }

            with patch.object(
                stock_price_service.stock_data_service,
                "get_multiple_prices",
                new=AsyncMock(return_value=api_results),
            ):
                mock_db.query.return_value.filter.return_value.first.return_value = None

                result = await stock_price_service.refresh_top_n_prices(mock_db, n=2)

        assert result["requested"] == 2
        assert result["success"] == 1
        assert result["failed"] == 1
        assert len(result["errors"]) > 0
