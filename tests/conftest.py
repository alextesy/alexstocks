"""Pytest configuration and shared fixtures."""

import os
import tempfile
from unittest.mock import Mock, patch

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.models import Article, Base, Ticker


@pytest.fixture(scope="session")
def test_engine():
    """Create test database engine."""
    # Use in-memory SQLite for tests
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    return engine


@pytest.fixture(scope="session")
def test_db_session(test_engine):
    """Create test database session."""
    Base.metadata.create_all(bind=test_engine)
    TestingSessionLocal = sessionmaker(
        autocommit=False, autoflush=False, bind=test_engine
    )
    session = TestingSessionLocal()
    yield session
    session.close()


@pytest.fixture
def db_session(test_engine, test_db_session):
    """Create a fresh database session for each test."""
    # Create a new session for each test (tables already created by test_db_session fixture)
    TestingSessionLocal = sessionmaker(
        autocommit=False, autoflush=False, bind=test_engine
    )
    session = TestingSessionLocal()

    yield session

    # Rollback any uncommitted changes and close session
    try:
        if session.in_transaction():
            session.rollback()
    finally:
        session.close()

    # Clean up all data from tables for test isolation
    # Since it's in-memory SQLite, data persists across sessions
    try:
        with test_engine.begin() as conn:
            # Try to delete data - ignore errors if tables don't exist
            for table in [
                "article_ticker",
                "article",
                "ticker",
                "reddit_thread",
                "stock_price",
                "stock_price_history",
                "stock_data_collection",
            ]:
                try:
                    conn.execute(text(f"DELETE FROM {table}"))
                except Exception:
                    pass  # Table might not exist yet
    except Exception:
        pass  # Ignore cleanup errors


@pytest.fixture
def sample_tickers():
    """Create sample ticker data for tests."""
    return [
        Ticker(symbol="AAPL", name="Apple Inc."),
        Ticker(symbol="TSLA", name="Tesla Inc."),
        Ticker(symbol="NVDA", name="NVIDIA Corporation"),
        Ticker(symbol="GME", name="GameStop Corp."),
        Ticker(symbol="AMC", name="AMC Entertainment Holdings Inc."),
        Ticker(symbol="SPY", name="SPDR S&P 500 ETF Trust"),
        Ticker(symbol="QQQ", name="Invesco QQQ Trust"),
        Ticker(symbol="MSFT", name="Microsoft Corporation"),
        Ticker(symbol="GOOGL", name="Alphabet Inc."),
        Ticker(symbol="AMZN", name="Amazon.com Inc."),
    ]


@pytest.fixture
def sample_articles():
    """Create sample article data for tests."""
    from datetime import UTC, datetime

    return [
        Article(
            source="reddit",
            url="https://reddit.com/r/wallstreetbets/comments/test1/",
            published_at=datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC),
            title="🚀 $GME to the moon! 💎🙌",
            text="Just bought more shares. This is not financial advice.",
            lang="en",
            reddit_id="test1",
            subreddit="wallstreetbets",
            author="diamond_hands_69",
            upvotes=1250,
            num_comments=89,
            reddit_url="https://reddit.com/r/wallstreetbets/comments/test1/",
        ),
        Article(
            source="reddit_comment",
            url="https://reddit.com/r/investing/comments/test2/comment1/",
            published_at=datetime(2024, 1, 1, 13, 0, 0, tzinfo=UTC),
            title="Comment",
            text="I'm bullish on $AAPL and $TSLA. Both are great tech stocks.",
            lang="en",
            reddit_id="comment1",
            subreddit="investing",
            author="tech_investor",
            upvotes=15,
            num_comments=0,
            reddit_url="https://reddit.com/r/investing/comments/test2/comment1/",
        ),
        Article(
            source="reddit",
            url="https://reddit.com/r/stocks/comments/test3/",
            published_at=datetime(2024, 1, 1, 14, 0, 0, tzinfo=UTC),
            title="Technical Analysis: NVDA showing bullish patterns",
            text="Looking at the charts for $NVDA. RSI is oversold, MACD showing bullish divergence.",
            lang="en",
            reddit_id="test3",
            subreddit="stocks",
            author="chart_analyst",
            upvotes=45,
            num_comments=12,
            reddit_url="https://reddit.com/r/stocks/comments/test3/",
        ),
    ]


@pytest.fixture
def mock_reddit_credentials():
    """Mock Reddit API credentials."""
    return {
        "client_id": "test_client_id",
        "client_secret": "test_client_secret",
        "user_agent": "test_user_agent",
    }


@pytest.fixture
def mock_reddit_submission():
    """Create a mock Reddit submission."""
    submission = Mock()
    submission.id = "test_submission_123"
    submission.title = "Test Reddit Post"
    submission.selftext = "This is a test post content"
    submission.permalink = "/r/wallstreetbets/comments/test_submission_123/"
    submission.created_utc = 1640995200  # 2022-01-01 00:00:00 UTC
    submission.author = Mock()
    submission.author.name = "testuser"
    submission.score = 100
    submission.num_comments = 50
    return submission


@pytest.fixture
def mock_reddit_comment():
    """Create a mock Reddit comment."""
    comment = Mock()
    comment.id = "test_comment_456"
    comment.body = "This is a test comment about $AAPL stock"
    comment.created_utc = 1640995200
    comment.author = Mock()
    comment.author.name = "commenter"
    comment.score = 5
    comment.permalink = (
        "/r/wallstreetbets/comments/test_submission_123/test_comment_456/"
    )
    return comment


@pytest.fixture
def mock_sentiment_service():
    """Mock sentiment analysis service."""
    service = Mock()
    service.analyze_sentiment.return_value = 0.5
    service.get_sentiment_label.return_value = "Neutral"
    service.analyze_with_label.return_value = (0.5, "Neutral")
    return service


@pytest.fixture
def mock_content_scraper():
    """Mock content scraper service."""
    scraper = Mock()
    scraper.max_workers = 5
    return scraper


@pytest.fixture
def mock_context_analyzer():
    """Mock context analyzer service."""
    analyzer = Mock()
    analyzer.analyze_ticker_relevance.return_value = (0.8, ["Strong context"])
    return analyzer


@pytest.fixture(autouse=True)
def mock_environment_variables():
    """Mock environment variables for tests."""
    with patch.dict(
        os.environ,
        {
            "DATABASE_URL": "sqlite:///:memory:",
            "REDDIT_CLIENT_ID": "test_client_id",
            "REDDIT_CLIENT_SECRET": "test_client_secret",
            "REDDIT_USER_AGENT": "test_user_agent",
            "SENTIMENT_USE_LLM": "false",
            "SENTIMENT_FALLBACK_VADER": "true",
            "SENTIMENT_DUAL_MODEL": "false",
        },
    ):
        yield


@pytest.fixture
def temp_file():
    """Create a temporary file for testing."""
    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".txt") as f:
        f.write("Test content")
        temp_path = f.name

    yield temp_path

    # Cleanup
    try:
        os.unlink(temp_path)
    except OSError:
        pass


# Test markers
def pytest_configure(config):
    """Configure pytest markers."""
    config.addinivalue_line("markers", "integration: mark test as integration test")
    config.addinivalue_line("markers", "performance: mark test as performance test")
    config.addinivalue_line("markers", "slow: mark test as slow running")
    config.addinivalue_line("markers", "reddit: mark test as requiring Reddit API")
    config.addinivalue_line("markers", "llm: mark test as requiring LLM models")


# Test collection hooks
def pytest_collection_modifyitems(config, items):
    """Modify test collection to add markers based on test names."""
    for item in items:
        # Add integration marker to tests with 'integration' in the name
        if "integration" in item.nodeid:
            item.add_marker(pytest.mark.integration)

        # Add performance marker to tests with 'performance' in the name
        if "performance" in item.nodeid:
            item.add_marker(pytest.mark.performance)

        # Add slow marker to tests that might be slow
        if any(
            keyword in item.nodeid.lower() for keyword in ["full", "complete", "batch"]
        ):
            item.add_marker(pytest.mark.slow)

        # Add reddit marker to Reddit-related tests
        if "reddit" in item.nodeid.lower():
            item.add_marker(pytest.mark.reddit)

        # Add llm marker to LLM-related tests
        if "llm" in item.nodeid.lower() or "hybrid" in item.nodeid.lower():
            item.add_marker(pytest.mark.llm)


# Pytest plugins
pytest_plugins: list[str] = []


# Custom fixtures for specific test scenarios
@pytest.fixture
def wallstreetbets_post():
    """Create a typical WallStreetBets post."""
    from datetime import UTC, datetime

    return Article(
        source="reddit",
        url="https://reddit.com/r/wallstreetbets/comments/wsb_post/",
        published_at=datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC),
        title="🚀 $GME to the moon! 💎🙌 Diamond hands!",
        text="Just YOLO'd my life savings into $GME. This is not financial advice. 🚀🚀🚀",
        lang="en",
        reddit_id="wsb_post",
        subreddit="wallstreetbets",
        author="diamond_hands_69",
        upvotes=2500,
        num_comments=150,
        reddit_url="https://reddit.com/r/wallstreetbets/comments/wsb_post/",
    )


@pytest.fixture
def technical_analysis_post():
    """Create a technical analysis post."""
    from datetime import UTC, datetime

    return Article(
        source="reddit",
        url="https://reddit.com/r/stocks/comments/tech_analysis/",
        published_at=datetime(2024, 1, 1, 14, 0, 0, tzinfo=UTC),
        title="Technical Analysis: AAPL showing bullish divergence",
        text="Looking at the RSI and MACD indicators for $AAPL. Support at $150, resistance at $180. Bullish pattern forming.",
        lang="en",
        reddit_id="tech_analysis",
        subreddit="stocks",
        author="chart_analyst",
        upvotes=75,
        num_comments=25,
        reddit_url="https://reddit.com/r/stocks/comments/tech_analysis/",
    )


@pytest.fixture
def earnings_discussion_post():
    """Create an earnings discussion post."""
    from datetime import UTC, datetime

    return Article(
        source="reddit",
        url="https://reddit.com/r/investing/comments/earnings_discussion/",
        published_at=datetime(2024, 1, 1, 16, 0, 0, tzinfo=UTC),
        title="MSFT Q4 Earnings Discussion",
        text="Microsoft $MSFT reported strong Q4 earnings. Revenue up 20% YoY. Azure growth continues to impress.",
        lang="en",
        reddit_id="earnings_discussion",
        subreddit="investing",
        author="earnings_analyst",
        upvotes=120,
        num_comments=45,
        reddit_url="https://reddit.com/r/investing/comments/earnings_discussion/",
    )
