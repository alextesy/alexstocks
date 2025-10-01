"""Tests for Reddit ingestion functionality."""

import os
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.models import Article, ArticleTicker, Ticker
from ingest.reddit import get_reddit_credentials, ingest_reddit_data
from ingest.reddit_parser import RedditParser


class TestRedditCredentials:
    """Test Reddit credentials handling."""

    def test_get_reddit_credentials_success(self):
        """Test successful credential retrieval."""
        with patch.dict(
            os.environ,
            {
                "REDDIT_CLIENT_ID": "test_client_id",
                "REDDIT_CLIENT_SECRET": "test_client_secret",
                "REDDIT_USER_AGENT": "TestBot/1.0",
            },
        ):
            client_id, client_secret, user_agent = get_reddit_credentials()
            assert client_id == "test_client_id"
            assert client_secret == "test_client_secret"
            assert user_agent == "TestBot/1.0"

    def test_get_reddit_credentials_default_user_agent(self):
        """Test default user agent when not provided."""
        with patch.dict(
            os.environ,
            {
                "REDDIT_CLIENT_ID": "test_client_id",
                "REDDIT_CLIENT_SECRET": "test_client_secret",
            },
            clear=True,
        ):
            client_id, client_secret, user_agent = get_reddit_credentials()
            assert user_agent == "MarketPulse/1.0 by MarketPulseBot"

    def test_get_reddit_credentials_missing_client_id(self):
        """Test error when client ID is missing."""
        with patch.dict(
            os.environ, {"REDDIT_CLIENT_SECRET": "test_client_secret"}, clear=True
        ):
            with pytest.raises(ValueError, match="Reddit API credentials not found"):
                get_reddit_credentials()

    def test_get_reddit_credentials_missing_client_secret(self):
        """Test error when client secret is missing."""
        with patch.dict(os.environ, {"REDDIT_CLIENT_ID": "test_client_id"}, clear=True):
            with pytest.raises(ValueError, match="Reddit API credentials not found"):
                get_reddit_credentials()


class TestRedditParser:
    """Test Reddit parser functionality."""

    def setup_method(self):
        """Set up test fixtures."""
        self.parser = RedditParser()

    def test_initialize_reddit(self):
        """Test Reddit client initialization."""
        with patch("praw.Reddit") as mock_reddit:
            self.parser.initialize_reddit("client_id", "client_secret", "user_agent")
            mock_reddit.assert_called_once_with(
                client_id="client_id",
                client_secret="client_secret",
                user_agent="user_agent",
            )

    def test_parse_submission(self):
        """Test parsing a Reddit submission."""
        # Mock Reddit submission
        mock_submission = MagicMock()
        mock_submission.id = "test123"
        mock_submission.title = "Test Post Title"
        mock_submission.selftext = "Test post content"
        mock_submission.author.name = "testuser"
        mock_submission.score = 100
        mock_submission.num_comments = 25
        mock_submission.created_utc = 1640995200  # 2022-01-01 00:00:00 UTC
        mock_submission.permalink = "/r/test/comments/test123/test_post/"

        article = self.parser.parse_submission(mock_submission, "test")

        assert article.source == "reddit"
        assert article.reddit_id == "test123"
        assert article.subreddit == "test"
        assert article.author == "testuser"
        assert article.upvotes == 100
        assert article.num_comments == 25
        assert article.title == "Test Post Title"
        assert article.text is not None
        assert "Test Post Title" in article.text
        assert "Test post content" in article.text
        assert (
            article.reddit_url
            == "https://reddit.com/r/test/comments/test123/test_post/"
        )
        assert article.published_at == datetime(2022, 1, 1, 0, 0, 0, tzinfo=UTC)

    def test_parse_submission_no_author(self):
        """Test parsing submission with no author."""
        mock_submission = MagicMock()
        mock_submission.id = "test123"
        mock_submission.title = "Test Post"
        mock_submission.selftext = ""
        mock_submission.author = None
        mock_submission.score = 0
        mock_submission.num_comments = 0
        mock_submission.created_utc = 1640995200
        mock_submission.permalink = "/r/test/comments/test123/test_post/"

        article = self.parser.parse_submission(mock_submission, "test")

        assert article.author is None
        assert article.upvotes == 0
        assert article.num_comments == 0

    def test_parse_submission_no_selftext(self):
        """Test parsing submission with no selftext."""
        mock_submission = MagicMock()
        mock_submission.id = "test123"
        mock_submission.title = "Test Post"
        mock_submission.selftext = ""
        mock_submission.author.name = "testuser"
        mock_submission.score = 50
        mock_submission.num_comments = 10
        mock_submission.created_utc = 1640995200
        mock_submission.permalink = "/r/test/comments/test123/test_post/"

        article = self.parser.parse_submission(mock_submission, "test")

        assert article.text == "Test Post"  # Only title, no selftext

    @patch("ingest.reddit_parser.RedditParser.fetch_subreddit_posts")
    def test_parse_subreddit_posts(self, mock_fetch):
        """Test parsing posts from a subreddit."""
        # Mock Reddit submissions
        mock_submission1 = MagicMock()
        mock_submission1.id = "post1"
        mock_submission1.title = "Post 1"
        mock_submission1.selftext = "Content 1"
        mock_submission1.author.name = "user1"
        mock_submission1.score = 100
        mock_submission1.num_comments = 10
        mock_submission1.created_utc = 1640995200
        mock_submission1.permalink = "/r/test/comments/post1/post_1/"

        mock_submission2 = MagicMock()
        mock_submission2.id = "post2"
        mock_submission2.title = "Post 2"
        mock_submission2.selftext = "Content 2"
        mock_submission2.author.name = "user2"
        mock_submission2.score = 200
        mock_submission2.num_comments = 20
        mock_submission2.created_utc = 1640995200
        mock_submission2.permalink = "/r/test/comments/post2/post_2/"

        mock_fetch.return_value = [mock_submission1, mock_submission2]

        articles = self.parser.parse_subreddit_posts(
            "test", limit=10, time_filter="day"
        )

        assert len(articles) == 2
        assert articles[0].reddit_id == "post1"
        assert articles[1].reddit_id == "post2"
        assert all(article.subreddit == "test" for article in articles)

    @patch("ingest.reddit_parser.RedditParser.parse_subreddit_posts")
    def test_parse_multiple_subreddits(self, mock_parse):
        """Test parsing posts from multiple subreddits."""
        # Mock articles from different subreddits
        mock_articles1 = [
            MagicMock(reddit_id="post1", subreddit="subreddit1"),
            MagicMock(reddit_id="post2", subreddit="subreddit1"),
        ]
        mock_articles2 = [MagicMock(reddit_id="post3", subreddit="subreddit2")]

        mock_parse.side_effect = [mock_articles1, mock_articles2]

        all_articles = self.parser.parse_multiple_subreddits(
            ["subreddit1", "subreddit2"], limit_per_subreddit=10, time_filter="day"
        )

        assert len(all_articles) == 3
        assert mock_parse.call_count == 2


class TestRedditIngestion:
    """Test Reddit ingestion integration."""

    def setup_method(self):
        """Set up test database."""
        # Create in-memory SQLite database for testing
        # Use JSON instead of JSONB for SQLite compatibility
        self.engine = create_engine("sqlite:///:memory:", echo=False)

        # Create tables with SQLite-compatible types
        from sqlalchemy import text

        with self.engine.connect() as conn:
            conn.execute(
                text(
                    """
                CREATE TABLE ticker (
                    symbol VARCHAR PRIMARY KEY,
                    name VARCHAR NOT NULL,
                    aliases TEXT  -- JSON as text for SQLite
                )
            """
                )
            )
            conn.execute(
                text(
                    """
                CREATE TABLE article (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source VARCHAR NOT NULL,
                    url VARCHAR UNIQUE NOT NULL,
                    published_at DATETIME NOT NULL,
                    title TEXT NOT NULL,
                    text TEXT,
                    lang VARCHAR,
                    sentiment FLOAT,
                    reddit_id VARCHAR(20) UNIQUE,
                    subreddit VARCHAR(50),
                    author VARCHAR(50),
                    upvotes INTEGER DEFAULT 0,
                    num_comments INTEGER DEFAULT 0,
                    reddit_url TEXT,
                    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            """
                )
            )
            conn.execute(
                text(
                    """
                CREATE TABLE article_ticker (
                    article_id INTEGER,
                    ticker VARCHAR,
                    confidence FLOAT DEFAULT 1.0,
                    PRIMARY KEY (article_id, ticker),
                    FOREIGN KEY (article_id) REFERENCES article(id) ON DELETE CASCADE,
                    FOREIGN KEY (ticker) REFERENCES ticker(symbol)
                )
            """
                )
            )
            conn.commit()

        self.SessionLocal = sessionmaker(bind=self.engine)

    def test_ingest_reddit_data_no_credentials(self):
        """Test ingestion fails without Reddit credentials."""
        with patch.dict(os.environ, {}, clear=True):
            with patch("ingest.reddit.SessionLocal", return_value=self.SessionLocal()):
                # Should not raise exception, just log error and return
                ingest_reddit_data(subreddits=["test"], limit_per_subreddit=10)

    @patch("ingest.reddit.get_reddit_credentials")
    @patch("ingest.reddit.RedditParser")
    @patch("ingest.reddit.TickerLinker")
    def test_ingest_reddit_data_success(
        self, mock_linker_class, mock_parser_class, mock_credentials
    ):
        """Test successful Reddit ingestion."""
        # Setup mocks
        mock_credentials.return_value = ("client_id", "client_secret", "user_agent")

        mock_parser = MagicMock()
        mock_parser_class.return_value = mock_parser

        # Mock articles
        mock_article = MagicMock()
        mock_article.reddit_id = "test123"
        mock_article.subreddit = "test"
        mock_parser.parse_multiple_subreddits.return_value = [mock_article]

        # Mock ticker linker
        mock_linker = MagicMock()
        mock_linker_class.return_value = mock_linker
        mock_linker.link_articles_to_db.return_value = [(mock_article, [])]

        # Add a test ticker to database
        db = self.SessionLocal()
        try:
            test_ticker = Ticker(symbol="TEST", name="Test Company", aliases=["TEST"])
            db.add(test_ticker)
            db.commit()
        finally:
            db.close()

        with patch("ingest.reddit.SessionLocal", return_value=self.SessionLocal()):
            ingest_reddit_data(subreddits=["test"], limit_per_subreddit=10)

        # Verify parser was initialized and called
        mock_parser.initialize_reddit.assert_called_once_with(
            "client_id", "client_secret", "user_agent"
        )
        mock_parser.parse_multiple_subreddits.assert_called_once_with(
            ["test"], 10, "day"
        )
        mock_linker.link_articles_to_db.assert_called_once()

    @patch("ingest.reddit.get_reddit_credentials")
    @patch("ingest.reddit.RedditParser")
    @patch("ingest.reddit.TickerLinker")
    def test_ingest_reddit_data_with_ticker_links(
        self, mock_linker_class, mock_parser_class, mock_credentials
    ):
        """Test Reddit ingestion with ticker links."""
        # Setup mocks
        mock_credentials.return_value = ("client_id", "client_secret", "user_agent")

        mock_parser = MagicMock()
        mock_parser_class.return_value = mock_parser

        # Mock article with Reddit data
        mock_article = Article(
            source="reddit",
            url="https://reddit.com/r/test/comments/test123/",
            published_at=datetime.now(UTC),
            title="Test Post",
            text="Test content",
            reddit_id="test123",
            subreddit="test",
            author="testuser",
            upvotes=100,
            num_comments=25,
        )
        mock_parser.parse_multiple_subreddits.return_value = [mock_article]

        # Mock ticker linker with links
        mock_linker = MagicMock()
        mock_linker_class.return_value = mock_linker
        mock_article_ticker = ArticleTicker(ticker="TEST", confidence=0.8)
        mock_linker.link_articles_to_db.return_value = [
            (mock_article, [mock_article_ticker])
        ]

        # Add a test ticker to database
        db = self.SessionLocal()
        try:
            test_ticker = Ticker(symbol="TEST", name="Test Company", aliases=["TEST"])
            db.add(test_ticker)
            db.commit()
        finally:
            db.close()

        with patch("ingest.reddit.SessionLocal", return_value=self.SessionLocal()):
            ingest_reddit_data(subreddits=["test"], limit_per_subreddit=10)

        # Verify the article was saved with Reddit data
        db = self.SessionLocal()
        try:
            saved_article = (
                db.query(Article).filter(Article.reddit_id == "test123").first()
            )
            assert saved_article is not None
            assert saved_article.subreddit == "test"
            assert saved_article.author == "testuser"
            assert saved_article.upvotes == 100
            assert saved_article.num_comments == 25
        finally:
            db.close()


if __name__ == "__main__":
    pytest.main([__file__])
