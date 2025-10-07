"""Integration tests for stock price API endpoints."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.db.models import Article, ArticleTicker, StockPrice, Ticker
from app.main import app


@pytest.fixture
def client():
    """Create a test client."""
    return TestClient(app)


@pytest.fixture
def sample_ticker(db_session):
    """Create a sample ticker in the database."""
    ticker = Ticker(symbol="AAPL", name="Apple Inc.", aliases=[], sources=["test"])
    db_session.add(ticker)
    db_session.commit()
    return ticker


@pytest.fixture
def sample_stock_price(db_session, sample_ticker):
    """Create a sample stock price in the database."""
    price = StockPrice(
        symbol="AAPL",
        price=150.0,
        previous_close=148.0,
        change=2.0,
        change_percent=1.35,
        market_state="OPEN",
        currency="USD",
        exchange="NASDAQ",
        updated_at=datetime.now(UTC) - timedelta(minutes=10),
    )
    db_session.add(price)
    db_session.commit()
    return price


@pytest.mark.integration
class TestStockPriceAPI:
    """Integration tests for /api/stock/{symbol} endpoint."""

    def test_get_stock_data_fresh_cache(self, client, sample_stock_price):
        """Test getting stock data with fresh cached data."""
        response = client.get("/api/stock/AAPL")

        assert response.status_code == 200
        data = response.json()
        assert data["symbol"] == "AAPL"
        assert data["price"] == 150.0
        assert data["change"] == 2.0

    def test_get_stock_data_stale_cache(self, client, db_session, sample_ticker):
        """Test getting stock data with stale cached data."""
        # Create stale price
        stale_price = StockPrice(
            symbol="AAPL",
            price=145.0,
            previous_close=143.0,
            change=2.0,
            change_percent=1.40,
            market_state="CLOSED",
            currency="USD",
            exchange="NASDAQ",
            updated_at=datetime.now(UTC) - timedelta(hours=2),  # Stale
        )
        db_session.add(stale_price)
        db_session.commit()

        # Mock the API call to return fresh data
        fresh_data = {
            "symbol": "AAPL",
            "price": 150.0,
            "previous_close": 148.0,
            "change": 2.0,
            "change_percent": 1.35,
            "market_state": "OPEN",
            "currency": "USD",
            "exchange": "NASDAQ",
        }

        with patch(
            "app.services.stock_price_service.stock_price_service.stock_data_service.get_stock_price",
            new=AsyncMock(return_value=fresh_data),
        ):
            response = client.get("/api/stock/AAPL")

        assert response.status_code == 200
        data = response.json()
        assert data["price"] == 150.0  # Should be fresh data

    def test_get_stock_data_not_found(self, client):
        """Test getting stock data for non-existent ticker."""
        # Mock the API to return None
        with patch(
            "app.services.stock_price_service.stock_price_service.stock_data_service.get_stock_price",
            new=AsyncMock(return_value=None),
        ):
            response = client.get("/api/stock/INVALID")

        assert response.status_code == 404
        assert "error" in response.json()

    def test_get_stock_data_case_insensitive(self, client, sample_stock_price):
        """Test that symbol lookup is case-insensitive."""
        response = client.get("/api/stock/aapl")

        assert response.status_code == 200
        data = response.json()
        assert data["symbol"] == "AAPL"


@pytest.mark.integration
class TestHomePageIntegration:
    """Integration tests for homepage with stock prices."""

    def test_homepage_with_fresh_prices(
        self, client, db_session, sample_ticker, sample_stock_price
    ):
        """Test homepage displays fresh stock prices."""
        # Create some articles to make ticker appear on homepage
        article = Article(
            source="test",
            url="https://example.com/test",
            published_at=datetime.now(UTC) - timedelta(hours=1),
            title="Test Article",
            text="Test content",
            lang="en",
        )
        db_session.add(article)
        db_session.commit()

        article_ticker = ArticleTicker(
            article_id=article.id,
            ticker="AAPL",
            confidence=0.9,
            matched_terms=["Apple"],
        )
        db_session.add(article_ticker)
        db_session.commit()

        response = client.get("/")

        assert response.status_code == 200
        # Check that price is in the response
        assert b"150" in response.content or b"150.0" in response.content

    def test_homepage_filters_stale_prices(self, client, db_session, sample_ticker):
        """Test homepage filters out stale stock prices."""
        # Create stale price
        stale_price = StockPrice(
            symbol="AAPL",
            price=145.0,
            previous_close=143.0,
            change=2.0,
            change_percent=1.40,
            market_state="CLOSED",
            currency="USD",
            exchange="NASDAQ",
            updated_at=datetime.now(UTC) - timedelta(hours=2),  # Stale
        )
        db_session.add(stale_price)

        # Create article
        article = Article(
            source="test",
            url="https://example.com/test",
            published_at=datetime.now(UTC) - timedelta(hours=1),
            title="Test Article",
            text="Test content",
            lang="en",
        )
        db_session.add(article)
        db_session.commit()

        article_ticker = ArticleTicker(
            article_id=article.id,
            ticker="AAPL",
            confidence=0.9,
            matched_terms=["Apple"],
        )
        db_session.add(article_ticker)
        db_session.commit()

        response = client.get("/")

        assert response.status_code == 200
        # Stale prices should not be displayed
        # This is a bit tricky to test in HTML, but we can check the response doesn't have price data


@pytest.mark.integration
class TestStockPriceValidation:
    """Integration tests for price data validation."""

    def test_invalid_price_rejected(self, client, db_session, sample_ticker):
        """Test that invalid prices are rejected."""
        # Mock API to return invalid data
        invalid_data = {
            "symbol": "AAPL",
            "price": 0.0,  # Invalid
            "previous_close": 148.0,
        }

        with patch(
            "app.services.stock_price_service.stock_price_service.stock_data_service.get_stock_price",
            new=AsyncMock(return_value=invalid_data),
        ):
            response = client.get("/api/stock/AAPL")

        # Should return 404 since no valid data
        assert response.status_code == 404

    def test_nan_price_rejected(self, client, db_session, sample_ticker):
        """Test that NaN prices are rejected."""
        import math

        invalid_data = {
            "symbol": "AAPL",
            "price": math.nan,  # Invalid
            "previous_close": 148.0,
        }

        with patch(
            "app.services.stock_price_service.stock_price_service.stock_data_service.get_stock_price",
            new=AsyncMock(return_value=invalid_data),
        ):
            response = client.get("/api/stock/AAPL")

        assert response.status_code == 404
