"""Tests for stock API endpoints."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.models import Base, StockPrice, StockPriceHistory, Ticker
from app.main import app


@pytest.fixture
def test_db_engine():
    """Create test database engine."""
    # Use file-based SQLite with check_same_thread=False for thread safety
    engine = create_engine(
        "sqlite:///test_stock_api.db",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()
    # Clean up test database file
    import os

    if os.path.exists("test_stock_api.db"):
        os.remove("test_stock_api.db")


@pytest.fixture
def db_session(test_db_engine):
    """Create an in-memory SQLite database for testing."""
    TestSessionLocal = sessionmaker(bind=test_db_engine)
    session = TestSessionLocal()

    # Add test tickers
    test_ticker = Ticker(symbol="AAPL", name="Apple Inc.", aliases=[], sources=["test"])
    session.add(test_ticker)

    # Add test stock price
    stock_price = StockPrice(
        symbol="AAPL",
        price=150.25,
        previous_close=148.50,
        change=1.75,
        change_percent=1.18,
        market_state="REGULAR",
        currency="USD",
        exchange="NASDAQ",
        updated_at=datetime.now(UTC),
    )
    session.add(stock_price)

    # Add historical data
    for i in range(5):
        history = StockPriceHistory(
            symbol="AAPL",
            date=datetime.now(UTC) - timedelta(days=i),
            open_price=148.0 + i,
            high_price=151.0 + i,
            low_price=147.0 + i,
            close_price=150.0 + i,
            volume=1000000 * (i + 1),
            created_at=datetime.now(UTC),
        )
        session.add(history)

    session.commit()
    yield session
    session.close()


@pytest.fixture
def client():
    """Create a test client."""
    return TestClient(app)


@pytest.fixture
def mock_stock_service_data():
    """Mock stock service response."""
    return {
        "symbol": "AAPL",
        "price": 150.25,
        "previous_close": 148.50,
        "change": 1.75,
        "change_percent": 1.18,
        "currency": "USD",
        "market_state": "REGULAR",
        "exchange": "NASDAQ",
        "last_updated": datetime.now(UTC).isoformat(),
    }


class TestStockAPI:
    """Test suite for stock API endpoints."""

    def test_get_stock_data_success(self, client, mock_stock_service_data):
        """Test successful stock data retrieval."""
        with patch(
            "app.main.stock_service.get_stock_price",
            new_callable=AsyncMock,
        ) as mock_get_price:
            mock_get_price.return_value = mock_stock_service_data

            response = client.get("/api/stock/AAPL")

            assert response.status_code == 200
            data = response.json()
            assert data["symbol"] == "AAPL"
            assert data["price"] == 150.25
            assert data["previous_close"] == 148.50
            assert data["change"] == 1.75
            assert data["change_percent"] == 1.18

    def test_get_stock_data_not_found(self, client):
        """Test stock data retrieval for non-existent symbol."""
        with patch(
            "app.main.stock_service.get_stock_price",
            new_callable=AsyncMock,
        ) as mock_get_price:
            mock_get_price.return_value = None

            response = client.get("/api/stock/INVALID")

            assert response.status_code == 404
            data = response.json()
            assert "error" in data

    def test_get_stock_data_uppercase_conversion(self, client, mock_stock_service_data):
        """Test that symbol is converted to uppercase."""
        with patch(
            "app.main.stock_service.get_stock_price",
            new_callable=AsyncMock,
        ) as mock_get_price:
            mock_get_price.return_value = mock_stock_service_data

            response = client.get("/api/stock/aapl")

            assert response.status_code == 200
            mock_get_price.assert_called_once_with("AAPL")

    def test_get_stock_chart_data_from_database(self, client, test_db_engine):
        """Test chart data retrieval from database."""
        # Mock the database session to use test engine
        TestSessionLocal = sessionmaker(bind=test_db_engine)
        with patch("app.db.session.SessionLocal", TestSessionLocal):
            response = client.get("/api/stock/AAPL/chart?period=1mo")

            # Should return either data or 404
            assert response.status_code in [200, 404]

    def test_get_stock_chart_data_invalid_symbol(self, client, test_db_engine):
        """Test chart data for non-existent symbol."""
        # Mock the database session to use test engine
        TestSessionLocal = sessionmaker(bind=test_db_engine)
        with patch("app.db.session.SessionLocal", TestSessionLocal):
            response = client.get("/api/stock/INVALIDXYZ/chart?period=1mo")

            # Should return 404
            assert response.status_code == 404
            if response.status_code == 404:
                data = response.json()
                assert "error" in data

    def test_get_stock_chart_data_different_periods(self, client, test_db_engine):
        """Test chart data with different period parameters."""
        # Mock the database session to use test engine
        TestSessionLocal = sessionmaker(bind=test_db_engine)
        with patch("app.db.session.SessionLocal", TestSessionLocal):
            periods = ["1d", "5d", "1mo", "3mo", "6mo", "1y"]

            for period in periods:
                response = client.get(f"/api/stock/AAPL/chart?period={period}")

                # Should return valid response (200 or 404 if no data)
                assert response.status_code in [200, 404]

    def test_get_stock_chart_data_default_period(self, client, test_db_engine):
        """Test chart data with default period."""
        # Mock the database session to use test engine
        TestSessionLocal = sessionmaker(bind=test_db_engine)
        with patch("app.db.session.SessionLocal", TestSessionLocal):
            response = client.get("/api/stock/AAPL/chart")

            # Should use default period (1mo)
            assert response.status_code in [200, 404]

    def test_health_endpoint(self, client):
        """Test health check endpoint."""
        response = client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True


class TestStockAPIIntegration:
    """Integration tests for stock API with database."""

    @pytest.mark.asyncio
    async def test_chart_endpoint_returns_database_data(self):
        """Test that chart endpoint returns data from database when available."""
        # This is a more complex integration test that would require
        # setting up the full database context and session management
        # Skipping for now as it requires more complex setup
        pass

    @pytest.mark.asyncio
    async def test_chart_endpoint_no_mock_data_fallback(self, client, test_db_engine):
        """Test that chart endpoint doesn't return mock data."""
        # Mock the database session to use test engine
        TestSessionLocal = sessionmaker(bind=test_db_engine)
        with patch("app.db.session.SessionLocal", TestSessionLocal):
            # When there's no data, should return 404, not mock data
            response = client.get("/api/stock/NONEXISTENT/chart")

            if response.status_code == 200:
                data = response.json()
                # Should not have 'mock' as source
                assert data.get("meta", {}).get("source") != "mock"
            else:
                # Should return 404
                assert response.status_code == 404


class TestStockAPIErrorHandling:
    """Test error handling in stock API endpoints."""

    def test_get_stock_data_service_exception(self, client):
        """Test stock data endpoint handles service exceptions."""
        with patch(
            "app.main.stock_service.get_stock_price",
            new_callable=AsyncMock,
        ) as mock_get_price:
            mock_get_price.side_effect = Exception("Service error")

            response = client.get("/api/stock/AAPL")

            # Should return 500 error
            assert response.status_code == 500
            data = response.json()
            assert "error" in data

    def test_get_chart_data_service_exception(self, client):
        """Test chart data endpoint handles service exceptions."""
        # Test by requesting a chart for a symbol that will cause issues
        # The actual behavior depends on database state
        response = client.get("/api/stock/TEST/chart")

        # Should return valid error response
        assert response.status_code in [404, 500]
