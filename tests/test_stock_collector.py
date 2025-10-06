"""Tests for stock price collector."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.collectors.stock_price_collector import StockPriceCollector
from app.db.models import (
    Base,
    StockDataCollection,
    StockPrice,
    StockPriceHistory,
    Ticker,
)


@pytest.fixture
def db_session():
    """Create an in-memory SQLite database for testing."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()

    # Add test tickers
    test_tickers = [
        Ticker(symbol="AAPL", name="Apple Inc.", aliases=[], sources=["test"]),
        Ticker(
            symbol="MSFT", name="Microsoft Corporation", aliases=[], sources=["test"]
        ),
        Ticker(symbol="GOOGL", name="Alphabet Inc.", aliases=[], sources=["test"]),
    ]
    for ticker in test_tickers:
        session.add(ticker)
    session.commit()

    yield session

    session.close()


@pytest.fixture
def collector():
    """Create a stock price collector instance."""
    return StockPriceCollector()


@pytest.fixture
def mock_stock_data():
    """Mock stock data response."""
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


@pytest.fixture
def mock_historical_data():
    """Mock historical data response."""
    return {
        "symbol": "AAPL",
        "period": "1mo",
        "data": [
            {
                "date": "2025-01-01",
                "open": 148.0,
                "high": 149.5,
                "low": 147.5,
                "close": 148.5,
                "price": 148.5,
                "volume": 1000000,
            },
            {
                "date": "2025-01-02",
                "open": 149.0,
                "high": 150.5,
                "low": 148.5,
                "close": 149.5,
                "price": 149.5,
                "volume": 1100000,
            },
            {
                "date": "2025-01-03",
                "open": 150.0,
                "high": 151.0,
                "low": 149.5,
                "close": 150.5,
                "price": 150.5,
                "volume": 1200000,
            },
        ],
        "meta": {"symbol": "AAPL", "source": "yahoo"},
    }


class TestStockPriceCollector:
    """Test suite for StockPriceCollector."""

    @pytest.mark.asyncio
    async def test_collect_current_prices_success(
        self, collector, db_session, mock_stock_data
    ):
        """Test successful current price collection."""
        # Mock the stock service
        with patch.object(
            collector.stock_service,
            "get_multiple_prices",
            new_callable=AsyncMock,
        ) as mock_get_prices:
            mock_get_prices.return_value = {
                "AAPL": mock_stock_data,
                "MSFT": {**mock_stock_data, "symbol": "MSFT", "price": 380.50},
                "GOOGL": {**mock_stock_data, "symbol": "GOOGL", "price": 140.75},
            }

            result = await collector.collect_current_prices(db_session)

            assert result["success"] == 3
            assert result["failed"] == 0
            assert len(result["errors"]) == 0

            # Check database
            stock_prices = db_session.query(StockPrice).all()
            assert len(stock_prices) == 3

            aapl_price = (
                db_session.query(StockPrice).filter(StockPrice.symbol == "AAPL").first()
            )
            assert aapl_price.price == 150.25
            assert aapl_price.previous_close == 148.50
            assert aapl_price.change == 1.75
            assert aapl_price.change_percent == 1.18

            # Check collection run
            collection_run = (
                db_session.query(StockDataCollection)
                .filter(StockDataCollection.collection_type == "current")
                .first()
            )
            assert collection_run.symbols_requested == 3
            assert collection_run.symbols_success == 3
            assert collection_run.symbols_failed == 0

    @pytest.mark.asyncio
    async def test_collect_current_prices_partial_failure(
        self, collector, db_session, mock_stock_data
    ):
        """Test current price collection with some failures."""
        with patch.object(
            collector.stock_service,
            "get_multiple_prices",
            new_callable=AsyncMock,
        ) as mock_get_prices:
            mock_get_prices.return_value = {
                "AAPL": mock_stock_data,
                "MSFT": None,  # Failed to fetch
                "GOOGL": {**mock_stock_data, "symbol": "GOOGL", "price": 140.75},
            }

            result = await collector.collect_current_prices(db_session)

            assert result["success"] == 2
            assert result["failed"] == 1
            assert len(result["errors"]) == 1

            # Check database
            stock_prices = db_session.query(StockPrice).all()
            assert len(stock_prices) == 2

    @pytest.mark.asyncio
    async def test_collect_current_prices_update_existing(
        self, collector, db_session, mock_stock_data
    ):
        """Test updating existing stock prices."""
        # Insert existing price
        existing_price = StockPrice(
            symbol="AAPL",
            price=145.00,
            previous_close=144.00,
            change=1.00,
            change_percent=0.69,
            market_state="CLOSED",
            currency="USD",
            exchange="NASDAQ",
            updated_at=datetime.now(UTC) - timedelta(hours=1),
        )
        db_session.add(existing_price)
        db_session.commit()

        with patch.object(
            collector.stock_service,
            "get_multiple_prices",
            new_callable=AsyncMock,
        ) as mock_get_prices:
            mock_get_prices.return_value = {
                "AAPL": mock_stock_data,
                "MSFT": {**mock_stock_data, "symbol": "MSFT", "price": 380.50},
                "GOOGL": {**mock_stock_data, "symbol": "GOOGL", "price": 140.75},
            }

            result = await collector.collect_current_prices(db_session)

            assert result["success"] == 3

            # Check that existing price was updated
            aapl_price = (
                db_session.query(StockPrice).filter(StockPrice.symbol == "AAPL").first()
            )
            assert aapl_price.price == 150.25  # New price
            assert aapl_price.previous_close == 148.50  # New previous close

    @pytest.mark.asyncio
    async def test_collect_current_prices_with_symbols_filter(
        self, collector, db_session, mock_stock_data
    ):
        """Test current price collection with specific symbols."""
        with patch.object(
            collector.stock_service,
            "get_multiple_prices",
            new_callable=AsyncMock,
        ) as mock_get_prices:
            mock_get_prices.return_value = {
                "AAPL": mock_stock_data,
            }

            result = await collector.collect_current_prices(
                db_session, symbols=["AAPL"]
            )

            assert result["success"] == 1
            mock_get_prices.assert_called_once()

    @pytest.mark.asyncio
    async def test_collect_historical_data_success(
        self, collector, db_session, mock_historical_data
    ):
        """Test successful historical data collection."""
        with patch.object(
            collector.stock_service,
            "get_historical_data",
            new_callable=AsyncMock,
        ) as mock_get_historical:
            mock_get_historical.return_value = mock_historical_data

            result = await collector.collect_historical_data(db_session)

            assert result["success"] == 3
            assert result["failed"] == 0

            # Check database
            history_records = db_session.query(StockPriceHistory).all()
            assert len(history_records) == 9  # 3 symbols × 3 data points

            # Check AAPL records
            aapl_records = (
                db_session.query(StockPriceHistory)
                .filter(StockPriceHistory.symbol == "AAPL")
                .order_by(StockPriceHistory.date)
                .all()
            )
            assert len(aapl_records) == 3
            assert aapl_records[0].close_price == 148.5
            assert aapl_records[0].volume == 1000000

    @pytest.mark.asyncio
    async def test_collect_historical_data_skip_recent(
        self, collector, db_session, mock_historical_data
    ):
        """Test historical data collection skips recent data."""
        # Insert recent historical data
        recent_record = StockPriceHistory(
            symbol="AAPL",
            date=datetime.now(UTC),
            close_price=150.00,
            volume=1000000,
            created_at=datetime.now(UTC),
        )
        db_session.add(recent_record)
        db_session.commit()

        with patch.object(
            collector.stock_service,
            "get_historical_data",
            new_callable=AsyncMock,
        ) as mock_get_historical:
            mock_get_historical.return_value = mock_historical_data

            result = await collector.collect_historical_data(db_session)

            # AAPL should be skipped (has recent data)
            assert result["success"] == 3  # Still counts as success

            # Mock should be called for MSFT and GOOGL but not AAPL (recent data)
            assert mock_get_historical.call_count >= 2

    @pytest.mark.asyncio
    async def test_collect_historical_data_force_refresh(
        self, collector, db_session, mock_historical_data
    ):
        """Test historical data collection with force refresh."""
        # Insert old historical data
        old_record = StockPriceHistory(
            symbol="AAPL",
            date=datetime.now(UTC) - timedelta(days=10),
            close_price=140.00,
            volume=900000,
            created_at=datetime.now(UTC) - timedelta(days=10),
        )
        db_session.add(old_record)
        db_session.commit()

        with patch.object(
            collector.stock_service,
            "get_historical_data",
            new_callable=AsyncMock,
        ) as mock_get_historical:
            mock_get_historical.return_value = mock_historical_data

            result = await collector.collect_historical_data(
                db_session, force_refresh=True
            )

            assert result["success"] == 3

            # Old record should be deleted and replaced
            aapl_records = (
                db_session.query(StockPriceHistory)
                .filter(StockPriceHistory.symbol == "AAPL")
                .all()
            )
            # Should only have 3 new records (old one deleted)
            assert len(aapl_records) == 3
            assert all(record.close_price != 140.00 for record in aapl_records)

    @pytest.mark.asyncio
    async def test_collect_historical_data_no_duplicates(
        self, collector, db_session, mock_historical_data
    ):
        """Test that historical data doesn't create duplicates."""
        with patch.object(
            collector.stock_service,
            "get_historical_data",
            new_callable=AsyncMock,
        ) as mock_get_historical:
            mock_get_historical.return_value = mock_historical_data

            # Collect twice
            await collector.collect_historical_data(db_session, symbols=["AAPL"])
            await collector.collect_historical_data(db_session, symbols=["AAPL"])

            # Should still only have 3 records (no duplicates)
            aapl_records = (
                db_session.query(StockPriceHistory)
                .filter(StockPriceHistory.symbol == "AAPL")
                .all()
            )
            assert len(aapl_records) == 3

    @pytest.mark.asyncio
    async def test_collect_historical_data_with_period(
        self, collector, db_session, mock_historical_data
    ):
        """Test historical data collection with specific period."""
        with patch.object(
            collector.stock_service,
            "get_historical_data",
            new_callable=AsyncMock,
        ) as mock_get_historical:
            mock_get_historical.return_value = mock_historical_data

            await collector.collect_historical_data(db_session, period="6mo")

            # Verify period was passed to service
            calls = mock_get_historical.call_args_list
            assert all(call[0][1] == "6mo" for call in calls)

    @pytest.mark.asyncio
    async def test_collection_run_tracking(
        self, collector, db_session, mock_stock_data
    ):
        """Test that collection runs are properly tracked."""
        with patch.object(
            collector.stock_service,
            "get_multiple_prices",
            new_callable=AsyncMock,
        ) as mock_get_prices:
            mock_get_prices.return_value = {
                "AAPL": mock_stock_data,
                "MSFT": None,
                "GOOGL": {**mock_stock_data, "symbol": "GOOGL"},
            }

            await collector.collect_current_prices(db_session)

            collection_run = (
                db_session.query(StockDataCollection)
                .filter(StockDataCollection.collection_type == "current")
                .first()
            )

            assert collection_run is not None
            assert collection_run.symbols_requested == 3
            assert collection_run.symbols_success == 2
            assert collection_run.symbols_failed == 1
            assert collection_run.completed_at is not None
            assert collection_run.duration_seconds is not None
            assert collection_run.duration_seconds > 0
