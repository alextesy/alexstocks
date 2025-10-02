"""Tests for Reddit scraping functionality."""

from datetime import UTC, datetime
from unittest.mock import Mock, patch

import pytest
from faker import Faker

from ingest.reddit_discussion_scraper import (
    RedditDiscussionScraper,
    get_reddit_credentials,
)

fake = Faker()


# NOTE: This test file has been streamlined to only test RedditDiscussionScraper
# (the base PRAW wrapper that's still in use).
#
# Removed test classes:
# - TestRedditParser: tested reddit_parser.py (deleted - legacy general post scraper)
# - TestRedditIngestion: tested reddit.py (deleted - legacy general post scraper)
#
# For comprehensive tests of the production scraper, see:
# - tests/test_reddit_scraper_new.py (new unified scraper)


class TestRedditDiscussionScraper:
    """Test Reddit discussion thread scraping."""

    def setup_method(self):
        """Set up test fixtures."""
        self.scraper = RedditDiscussionScraper()
        self.mock_reddit = Mock()
        self.scraper.reddit = self.mock_reddit

    def test_initialize_reddit(self):
        """Test Reddit client initialization."""
        client_id = "test_client_id"
        client_secret = "test_client_secret"
        user_agent = "test_user_agent"

        with patch("praw.Reddit") as mock_praw:
            self.scraper.initialize_reddit(client_id, client_secret, user_agent)

            mock_praw.assert_called_once_with(
                client_id=client_id, client_secret=client_secret, user_agent=user_agent
            )

    def test_find_daily_discussion_threads(self):
        """Test finding daily discussion threads."""
        # Mock subreddit
        mock_subreddit = Mock()
        mock_thread1 = Mock()
        mock_thread1.title = "Daily Discussion Thread for October 01, 2025"
        mock_thread1.created_utc = 1696156800
        mock_thread1.num_comments = 1000

        mock_thread2 = Mock()
        mock_thread2.title = "Weekend Discussion Thread"
        mock_thread2.created_utc = 1696243200
        mock_thread2.num_comments = 500

        mock_thread3 = Mock()
        mock_thread3.title = "Some Other Post"
        mock_thread3.created_utc = 1696329600
        mock_thread3.num_comments = 50

        # Mock subreddit.hot() and subreddit.top() to return all posts
        mock_subreddit.hot.return_value = [mock_thread1, mock_thread2, mock_thread3]
        mock_subreddit.top.return_value = []  # Return empty for top to avoid duplicates

        self.mock_reddit.subreddit.return_value = mock_subreddit

        # Find threads
        threads = self.scraper.find_daily_discussion_threads("wallstreetbets", limit=10)

        # Should find only daily/weekend discussion threads
        assert len(threads) == 2
        assert mock_thread1 in threads
        assert mock_thread2 in threads
        assert mock_thread3 not in threads

    def test_parse_comment_to_article(self):
        """Test parsing a Reddit comment into Article model."""
        # Create mock comment
        mock_comment = Mock()
        mock_comment.id = "comment123"
        mock_comment.body = "This is a test comment about $AAPL"
        mock_comment.created_utc = 1640995200  # 2022-01-01 00:00:00 UTC
        mock_comment.author = Mock()
        mock_comment.author.name = "commenter"
        mock_comment.score = 5
        mock_comment.subreddit.display_name = "wallstreetbets"
        mock_comment.permalink = "/r/wallstreetbets/comments/thread123/test/comment123"

        # Create mock submission
        mock_submission = Mock()
        mock_submission.id = "thread123"
        mock_submission.title = "Daily Discussion"
        mock_submission.subreddit.display_name = "wallstreetbets"
        mock_submission.permalink = "/r/wallstreetbets/comments/thread123/"

        # Parse comment
        article = self.scraper.parse_comment_to_article(mock_comment, mock_submission)

        # Assertions
        assert article.source == "reddit_comment"
        assert article.title == "Comment in: Daily Discussion"  # Note: has "Comment in: " prefix
        assert article.text == "This is a test comment about $AAPL"
        assert article.reddit_id == "comment123"
        assert article.subreddit == "wallstreetbets"
        assert article.author == "commenter"
        assert article.upvotes == 5
        assert article.published_at == datetime(2022, 1, 1, 0, 0, 0, tzinfo=UTC)


class TestRedditCredentials:
    """Test Reddit credential loading."""

    @patch.dict(
        "os.environ",
        {
            "REDDIT_CLIENT_ID": "test_id",
            "REDDIT_CLIENT_SECRET": "test_secret",
            "REDDIT_USER_AGENT": "MarketPulse/1.0 by test",
        },
    )
    def test_get_reddit_credentials_success(self):
        """Test successful credential loading."""
        client_id, client_secret, user_agent = get_reddit_credentials()
        assert client_id == "test_id"
        assert client_secret == "test_secret"
        assert "MarketPulse" in user_agent

    @patch.dict("os.environ", {}, clear=True)
    def test_get_reddit_credentials_missing(self):
        """Test error when credentials are missing."""
        with pytest.raises(ValueError, match="Reddit API credentials not found"):
            get_reddit_credentials()


class TestRedditScrapingIntegration:
    """Integration tests for Reddit scraping (requires credentials)."""

    @pytest.mark.integration
    def test_initialize_reddit_with_real_credentials(self):
        """Test initializing Reddit with real credentials (integration test)."""
        try:
            client_id, client_secret, user_agent = get_reddit_credentials()

            scraper = RedditDiscussionScraper()
            scraper.initialize_reddit(client_id, client_secret, user_agent)

            assert scraper.reddit is not None
        except ValueError:
            # Skip if credentials not configured
            pytest.skip("Reddit credentials not configured")

    @pytest.mark.integration
    def test_find_threads_with_real_api(self):
        """Test finding threads with real Reddit API (integration test)."""
        try:
            client_id, client_secret, user_agent = get_reddit_credentials()

            scraper = RedditDiscussionScraper()
            scraper.initialize_reddit(client_id, client_secret, user_agent)

            threads = scraper.find_daily_discussion_threads("wallstreetbets", limit=5)

            # Should find at least some threads (may be 0 if none exist today)
            assert isinstance(threads, list)
            if threads:
                assert hasattr(threads[0], "title")
                assert hasattr(threads[0], "id")
        except ValueError:
            pytest.skip("Reddit credentials not configured")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
