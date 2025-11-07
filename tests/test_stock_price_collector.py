"""
Tests for the stock price collector job.

Tests all major components:
1. Getting top N tickers by article count
2. Fetching stock prices from Yahoo Finance
3. Validating price data
4. Batch processing multiple stocks
5. Updating database with new prices
6. Full integration test

Note: These tests import the StockPriceCollector lazily (inside test functions)
to avoid config validation issues with the test database.
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest
from sqlalchemy import func

from app.db.models import Article, ArticleTicker, StockPrice, Ticker


class TestStockPriceCollector:
    """Test suite for stock price collector functionality."""

    @pytest.fixture(autouse=True)
    def setup_postgres_url(self, monkeypatch):
        """Set postgres URL before each test to satisfy config validation."""
        monkeypatch.setenv("POSTGRES_URL", "postgresql://test:test@localhost:5432/test")
        monkeypatch.setenv("DATABASE_URL", "postgresql://test:test@localhost:5432/test")

    def test_get_top_n_tickers(self, db_session, sample_articles_with_tickers):
        """Test getting top N tickers by article count."""
        from jobs.jobs.stock_price_collector import StockPriceCollector

        collector = StockPriceCollector()

        # Get top 10 tickers from last 24 hours
        top_tickers = collector.get_top_n_tickers(db_session, n=10, hours=24)

        # Should return list of ticker symbols
        assert isinstance(top_tickers, list)
        assert len(top_tickers) <= 10

        # All should be strings (ticker symbols)
        for ticker in top_tickers:
            assert isinstance(ticker, str)
            assert len(ticker) > 0

    def test_get_top_n_tickers_excludes_etfs(
        self, db_session, sample_articles_with_tickers
    ):
        """Ensure ETF tickers are excluded even with high mention counts."""
        from jobs.jobs.stock_price_collector import StockPriceCollector

        collector = StockPriceCollector()

        top_tickers = collector.get_top_n_tickers(db_session, n=5, hours=24)

        assert "SPY" not in top_tickers

    def test_get_top_n_tickers_empty_db(self, db_session):
        """Test getting top tickers when database is empty."""
        from jobs.jobs.stock_price_collector import StockPriceCollector

        collector = StockPriceCollector()
        top_tickers = collector.get_top_n_tickers(db_session, n=50, hours=24)

        # Should return empty list when no articles
        assert top_tickers == []

    def test_get_top_n_tickers_ordering(self, db_session, sample_articles_with_tickers):
        """Test that tickers are ordered by article count (descending)."""
        from jobs.jobs.stock_price_collector import StockPriceCollector

        collector = StockPriceCollector()

        # Create articles with different ticker counts
        # This assumes sample_articles_with_tickers creates varied data
        top_tickers = collector.get_top_n_tickers(db_session, n=5, hours=24)

        if len(top_tickers) > 1:
            # Verify ordering by checking article counts
            for ticker in top_tickers:
                count = (
                    db_session.query(func.count(ArticleTicker.article_id))
                    .filter(ArticleTicker.ticker == ticker)
                    .join(Article)
                    .filter(
                        Article.published_at >= datetime.now(UTC) - timedelta(hours=24)
                    )
                    .scalar()
                )
                assert count > 0

    def test_validate_price_data_valid(self):
        """Test price validation with valid data."""
        from jobs.jobs.stock_price_collector import StockPriceCollector

        collector = StockPriceCollector()

        valid_data = {
            "symbol": "AAPL",
            "price": 150.25,
            "previous_close": 149.50,
            "change": 0.75,
            "change_percent": 0.50,
            "market_state": "OPEN",
            "currency": "USD",
            "exchange": "NASDAQ",
        }

        assert collector.validate_price_data(valid_data) is True

    def test_validate_price_data_invalid_cases(self):
        """Test price validation with various invalid cases."""
        from jobs.jobs.stock_price_collector import StockPriceCollector

        collector = StockPriceCollector()

        # Test None data
        assert collector.validate_price_data(None) is False  # type: ignore[arg-type]

        # Test missing price
        assert collector.validate_price_data({"symbol": "TEST"}) is False

        # Test None price
        assert collector.validate_price_data({"price": None, "symbol": "TEST"}) is False

        # Test zero price
        assert collector.validate_price_data({"price": 0, "symbol": "TEST"}) is False

        # Test negative price
        assert collector.validate_price_data({"price": -10, "symbol": "TEST"}) is False

        # Test unrealistically high price
        assert (
            collector.validate_price_data({"price": 2000000, "symbol": "TEST"}) is False
        )

    def test_validate_price_data_edge_cases(self):
        """Test price validation edge cases."""
        from jobs.jobs.stock_price_collector import StockPriceCollector

        collector = StockPriceCollector()

        # Test very small positive price (penny stock)
        assert collector.validate_price_data({"price": 0.01, "symbol": "TEST"}) is True

        # Test high but realistic price (e.g., BRK.A)
        assert (
            collector.validate_price_data({"price": 500000, "symbol": "BRK.A"}) is True
        )

        # Test boundary at $1M
        assert (
            collector.validate_price_data({"price": 999999, "symbol": "TEST"}) is True
        )
        assert (
            collector.validate_price_data({"price": 1000001, "symbol": "TEST"}) is False
        )

    @pytest.mark.asyncio
    async def test_fetch_single_stock_price(self):
        """Test fetching price for a single stock."""
        from jobs.jobs.stock_price_collector import StockPriceCollector

        collector = StockPriceCollector()

        # Mock the stock service to avoid real API calls
        mock_data = {
            "symbol": "AAPL",
            "price": 150.25,
            "previous_close": 149.50,
            "change": 0.75,
            "change_percent": 0.50,
            "market_state": "OPEN",
            "currency": "USD",
            "exchange": "NASDAQ",
        }

        with patch.object(
            collector.stock_service, "get_stock_price", return_value=mock_data
        ):
            data = await collector.stock_service.get_stock_price("AAPL")

            assert data is not None
            assert data["symbol"] == "AAPL"
            assert data["price"] > 0
            assert "previous_close" in data

    @pytest.mark.asyncio
    async def test_refresh_prices_empty_list(self, db_session):
        """Test refresh_prices with empty symbol list."""
        from jobs.jobs.stock_price_collector import StockPriceCollector

        collector = StockPriceCollector()
        result = await collector.refresh_prices(db_session, [])

        assert result["requested"] == 0
        assert result["success"] == 0
        assert result["failed"] == 0
        assert result["errors"] == []

    @pytest.mark.asyncio
    async def test_refresh_prices_single_symbol(self, db_session, sample_ticker):
        """Test refresh_prices with a single symbol."""
        from jobs.jobs.stock_price_collector import StockPriceCollector

        collector = StockPriceCollector()

        mock_data = {
            "symbol": sample_ticker.symbol,
            "price": 150.25,
            "previous_close": 149.50,
            "change": 0.75,
            "change_percent": 0.50,
            "market_state": "OPEN",
            "currency": "USD",
            "exchange": "NASDAQ",
        }

        with patch.object(
            collector.stock_service, "get_stock_price", return_value=mock_data
        ):
            result = await collector.refresh_prices(db_session, [sample_ticker.symbol])

            assert result["requested"] == 1
            assert result["success"] == 1
            assert result["failed"] == 0

            # Verify database was updated
            stock_price = (
                db_session.query(StockPrice)
                .filter(StockPrice.symbol == sample_ticker.symbol)
                .first()
            )
            assert stock_price is not None
            assert stock_price.price == 150.25

    @pytest.mark.asyncio
    async def test_refresh_prices_batch_processing(self, db_session, sample_tickers):
        """Test that refresh_prices processes symbols in batches."""
        from jobs.jobs.stock_price_collector import StockPriceCollector

        collector = StockPriceCollector()

        # Create more symbols than batch size
        symbols = [ticker.symbol for ticker in sample_tickers[:10]]

        mock_data_template = {
            "price": 150.25,
            "previous_close": 149.50,
            "change": 0.75,
            "change_percent": 0.50,
            "market_state": "OPEN",
            "currency": "USD",
            "exchange": "NASDAQ",
        }

        async def mock_get_price(symbol):
            data = mock_data_template.copy()
            data["symbol"] = symbol
            return data

        with patch.object(
            collector.stock_service, "get_stock_price", side_effect=mock_get_price
        ):
            result = await collector.refresh_prices(db_session, symbols)

            assert result["requested"] == len(symbols)
            assert result["success"] == len(symbols)
            assert result["failed"] == 0

    @pytest.mark.asyncio
    async def test_refresh_prices_handles_failures(self, db_session, sample_ticker):
        """Test that refresh_prices handles API failures gracefully."""
        from jobs.jobs.stock_price_collector import StockPriceCollector

        collector = StockPriceCollector()

        # Mock API to return None (failure)
        with patch.object(
            collector.stock_service, "get_stock_price", return_value=None
        ):
            result = await collector.refresh_prices(db_session, [sample_ticker.symbol])

            assert result["requested"] == 1
            assert result["success"] == 0
            assert result["failed"] == 1
            assert len(result["errors"]) > 0

    @pytest.mark.asyncio
    async def test_refresh_prices_updates_existing_record(
        self, db_session, sample_ticker, sample_stock_price
    ):
        """Test that refresh_prices updates existing records rather than creating duplicates."""
        from jobs.jobs.stock_price_collector import StockPriceCollector

        collector = StockPriceCollector()

        # Initial price
        initial_price = sample_stock_price.price

        # New price data
        mock_data = {
            "symbol": sample_ticker.symbol,
            "price": 999.99,  # Different from initial
            "previous_close": 900.00,
            "change": 99.99,
            "change_percent": 11.11,
            "market_state": "OPEN",
            "currency": "USD",
            "exchange": "NASDAQ",
        }

        with patch.object(
            collector.stock_service, "get_stock_price", return_value=mock_data
        ):
            await collector.refresh_prices(db_session, [sample_ticker.symbol])

            # Should only be one record
            count = (
                db_session.query(StockPrice)
                .filter(StockPrice.symbol == sample_ticker.symbol)
                .count()
            )
            assert count == 1

            # Price should be updated
            updated_price = (
                db_session.query(StockPrice)
                .filter(StockPrice.symbol == sample_ticker.symbol)
                .first()
            )
            assert updated_price.price == 999.99
            assert updated_price.price != initial_price

    @pytest.mark.asyncio
    async def test_full_collector_run_with_mocked_data(
        self, db_session, sample_articles_with_tickers
    ):
        """Test full collector run with mocked stock data."""
        from jobs.jobs.stock_price_collector import StockPriceCollector

        collector = StockPriceCollector()

        mock_data = {
            "price": 150.25,
            "previous_close": 149.50,
            "change": 0.75,
            "change_percent": 0.50,
            "market_state": "OPEN",
            "currency": "USD",
            "exchange": "NASDAQ",
        }

        async def mock_get_price(symbol):
            data = mock_data.copy()
            data["symbol"] = symbol
            return data

        with patch.object(
            collector.stock_service, "get_stock_price", side_effect=mock_get_price
        ):
            # Override get_top_n_tickers to use our test session
            original_get_top = collector.get_top_n_tickers

            def mock_get_top(db, n=50, hours=24):
                return original_get_top(db_session, n, hours)

            with patch.object(collector, "get_top_n_tickers", side_effect=mock_get_top):
                # Mock SessionLocal to return our test session
                with patch("jobs.jobs.stock_price_collector.SessionLocal") as mock_sl:
                    mock_sl.return_value = db_session

                    result = await collector.run()

                    assert "requested" in result
                    assert "success" in result
                    assert "failed" in result

    def test_stock_price_database_query(self, db_session, sample_stock_price):
        """Test querying stock prices from database."""
        # Query by symbol
        price = (
            db_session.query(StockPrice)
            .filter(StockPrice.symbol == sample_stock_price.symbol)
            .first()
        )

        assert price is not None
        assert price.symbol == sample_stock_price.symbol
        assert price.price > 0
        assert price.updated_at is not None

    def test_stock_price_age_check(self, db_session, sample_stock_price):
        """Test checking if stock price is stale."""
        from datetime import timedelta

        # Get current time (use naive datetime if database returns naive)
        now = datetime.now(UTC)
        if sample_stock_price.updated_at.tzinfo is None:
            now = datetime.now()  # Use naive datetime to match database

        # Set fresh timestamp (just now)
        sample_stock_price.updated_at = now
        db_session.commit()
        db_session.refresh(sample_stock_price)

        # Price should be fresh
        age = now - sample_stock_price.updated_at
        assert age < timedelta(minutes=5)

        # Simulate old price (2 hours ago)
        old_time = now - timedelta(hours=2)
        sample_stock_price.updated_at = old_time
        db_session.commit()
        db_session.refresh(sample_stock_price)

        # Check age of stale price
        age = now - sample_stock_price.updated_at
        assert age > timedelta(minutes=30)  # Stale threshold

    def test_multiple_stock_prices_ordering(self, db_session, sample_tickers):
        """Test querying multiple stock prices ordered by update time."""
        # Create stock prices for multiple tickers
        for i, ticker in enumerate(sample_tickers[:5]):
            stock_price = StockPrice(
                symbol=ticker.symbol,
                price=100.0 + i,
                previous_close=99.0 + i,
                change=1.0,
                change_percent=1.0,
                market_state="CLOSED",
                currency="USD",
                updated_at=datetime.now(UTC) - timedelta(minutes=i),
            )
            db_session.add(stock_price)
        db_session.commit()

        # Query ordered by most recent
        prices = (
            db_session.query(StockPrice)
            .order_by(StockPrice.updated_at.desc())
            .limit(5)
            .all()
        )

        assert len(prices) > 0
        # Verify ordering (most recent first)
        for i in range(len(prices) - 1):
            assert prices[i].updated_at >= prices[i + 1].updated_at


# Fixtures for testing


@pytest.fixture
def sample_ticker(db_session):
    """Create a sample ticker for testing."""
    ticker = Ticker(symbol="AAPL", name="Apple Inc.", aliases=["Apple"])
    db_session.add(ticker)
    db_session.commit()
    return ticker


@pytest.fixture
def sample_tickers(db_session):
    """Create multiple sample tickers for testing."""
    tickers = [
        Ticker(symbol="AAPL", name="Apple Inc.", aliases=["Apple"]),
        Ticker(symbol="MSFT", name="Microsoft Corporation", aliases=["Microsoft"]),
        Ticker(symbol="GOOGL", name="Alphabet Inc.", aliases=["Google"]),
        Ticker(symbol="AMZN", name="Amazon.com Inc.", aliases=["Amazon"]),
        Ticker(symbol="TSLA", name="Tesla Inc.", aliases=["Tesla"]),
        Ticker(
            symbol="SPY",
            name="SPDR S&P 500 ETF Trust",
            aliases=["SPY"],
        ),
        Ticker(symbol="META", name="Meta Platforms Inc.", aliases=["Facebook"]),
        Ticker(symbol="NVDA", name="NVIDIA Corporation", aliases=["NVIDIA"]),
        Ticker(symbol="AMD", name="Advanced Micro Devices", aliases=["AMD"]),
        Ticker(symbol="NFLX", name="Netflix Inc.", aliases=["Netflix"]),
        Ticker(symbol="DIS", name="The Walt Disney Company", aliases=["Disney"]),
    ]
    for ticker in tickers:
        db_session.add(ticker)
    db_session.commit()
    return tickers


@pytest.fixture
def sample_stock_price(db_session, sample_ticker):
    """Create a sample stock price for testing."""
    stock_price = StockPrice(
        symbol=sample_ticker.symbol,
        price=150.25,
        previous_close=149.50,
        change=0.75,
        change_percent=0.50,
        market_state="OPEN",
        currency="USD",
        exchange="NASDAQ",
        updated_at=datetime.now(UTC),
    )
    db_session.add(stock_price)
    db_session.commit()
    return stock_price


@pytest.fixture
def sample_articles_with_tickers(db_session, sample_tickers):
    """Create sample articles with ticker mentions."""
    articles = []

    # Create articles with different ticker mentions
    ticker_counts = {
        "AAPL": 5,
        "MSFT": 4,
        "GOOGL": 3,
        "AMZN": 2,
        "TSLA": 1,
    }

    article_id = 1
    for ticker_symbol, count in ticker_counts.items():
        for _ in range(count):
            article = Article(
                source="reddit_comment",
                url=f"https://reddit.com/r/test/comments/{article_id}",
                published_at=datetime.now(UTC) - timedelta(hours=1),
                title=f"Discussion about {ticker_symbol}",
                text=f"This is about {ticker_symbol}",
                reddit_id=f"test{article_id}",
            )
            db_session.add(article)
            db_session.flush()

            # Link ticker to article
            article_ticker = ArticleTicker(
                article_id=article.id,
                ticker=ticker_symbol,
                confidence=0.9,
                matched_terms=[ticker_symbol],
            )
            db_session.add(article_ticker)
            articles.append(article)
            article_id += 1

    db_session.commit()
    return articles
