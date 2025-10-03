"""Tests for the production Reddit scraper."""

from datetime import UTC, datetime
from unittest.mock import Mock, patch

import pytest

from ingest.reddit_scraper import RateLimiter, RedditScraper, ScrapeStats


class TestRateLimiter:
    """Test the RateLimiter class."""

    def test_rate_limiter_init(self):
        """Test RateLimiter initialization."""
        limiter = RateLimiter()
        assert limiter.requests_per_minute == 90
        assert limiter.request_times == []

    def test_rate_limiter_check_and_wait_empty(self):
        """Test rate limiter with no previous requests."""
        limiter = RateLimiter()
        limiter.check_and_wait()  # Should not raise or block
        assert len(limiter.request_times) == 1

    def test_rate_limiter_handle_429_error(self):
        """Test handling of 429 errors."""
        limiter = RateLimiter()

        # Test 429 string detection
        error = Exception("HTTP 429 Too Many Requests")
        should_retry, sleep_time = limiter.handle_rate_limit_error(error, 0)
        assert should_retry is True
        assert sleep_time > 0

        # Test max retries
        should_retry, sleep_time = limiter.handle_rate_limit_error(error, 3)
        assert should_retry is False

    def test_rate_limiter_exponential_backoff(self):
        """Test exponential backoff calculation."""
        limiter = RateLimiter()
        error = Exception("429 rate limit")

        # First attempt: 30s base
        _, sleep1 = limiter.handle_rate_limit_error(error, 0)
        assert 30 <= sleep1 <= 35  # 30s + up to 5s jitter

        # Second attempt: 60s base
        _, sleep2 = limiter.handle_rate_limit_error(error, 1)
        assert 60 <= sleep2 <= 65

        # Third attempt: 120s base
        _, sleep3 = limiter.handle_rate_limit_error(error, 2)
        assert 120 <= sleep3 <= 125


class TestRedditScraper:
    """Test the RedditScraper class."""

    def setup_method(self):
        """Set up test fixtures."""
        self.scraper = RedditScraper()
        self.mock_reddit = Mock()
        self.scraper.reddit = self.mock_reddit
        self.scraper.discussion_scraper.reddit = self.mock_reddit

    def test_scraper_init(self):
        """Test scraper initialization."""
        scraper = RedditScraper()
        assert scraper.max_scraping_workers == 5
        assert scraper.batch_save_interval == 200
        assert scraper.rate_limiter.requests_per_minute == 90

    def test_scraper_custom_config(self):
        """Test scraper with custom configuration."""
        scraper = RedditScraper(
            max_scraping_workers=10,
            batch_save_interval=100,
            requests_per_minute=80,
        )
        assert scraper.max_scraping_workers == 10
        assert scraper.batch_save_interval == 100
        assert scraper.rate_limiter.requests_per_minute == 80

    @patch("praw.Reddit")
    def test_initialize_reddit(self, mock_praw):
        """Test Reddit initialization."""
        scraper = RedditScraper()
        scraper.initialize_reddit("client_id", "client_secret", "user_agent")

        # PRAW should be initialized via discussion_scraper
        mock_praw.assert_called_once()

    def test_find_threads_by_date(self):
        """Test finding threads by specific date."""
        # Create mock threads with different dates
        thread1 = Mock()
        thread1.id = "thread1"
        thread1.title = "Daily Discussion - Oct 1"
        thread1.created_utc = datetime(2025, 10, 1, 12, 0, tzinfo=UTC).timestamp()

        thread2 = Mock()
        thread2.id = "thread2"
        thread2.title = "Weekend Discussion - Oct 2"
        thread2.created_utc = datetime(2025, 10, 2, 12, 0, tzinfo=UTC).timestamp()

        thread3 = Mock()
        thread3.id = "thread3"
        thread3.title = "Daily Discussion - Oct 3"
        thread3.created_utc = datetime(2025, 10, 3, 12, 0, tzinfo=UTC).timestamp()

        self.scraper.discussion_scraper.find_daily_discussion_threads = Mock(
            return_value=[thread1, thread2, thread3]
        )

        # Find threads for Oct 2
        target_date = datetime(2025, 10, 2, tzinfo=UTC)
        threads = self.scraper.find_threads_by_date("wallstreetbets", target_date)

        # Should only return thread2
        assert len(threads) == 1
        assert threads[0].id == "thread2"

    def test_get_existing_comment_ids(self):
        """Test getting existing comment IDs."""
        from unittest.mock import MagicMock

        from app.db.session import SessionLocal

        with patch.object(SessionLocal, "__call__") as mock_session_factory:
            mock_db = MagicMock()
            mock_session_factory.return_value = mock_db

            # Mock the execute result
            mock_result = MagicMock()
            mock_result.scalars().all.return_value = ["id1", "id2", "id3"]
            mock_db.execute.return_value = mock_result

            # This test is more of a smoke test since it requires DB
            # In a real test, you'd use a test database or more sophisticated mocking

    def test_extract_comments_with_retry_success(self):
        """Test successful comment extraction."""
        # Create mock submission
        mock_submission = Mock()
        mock_submission.title = "Daily Discussion"
        mock_submission.num_comments = 100

        # Create mock comments
        mock_comment1 = Mock()
        mock_comment1.body = "Test comment 1"
        mock_comment1.id = "c1"

        mock_comment2 = Mock()
        mock_comment2.body = "[deleted]"
        mock_comment2.id = "c2"

        mock_comment3 = Mock()
        mock_comment3.body = "Test comment 3"
        mock_comment3.id = "c3"

        mock_submission.comments.replace_more = Mock()
        mock_submission.comments.list.return_value = [
            mock_comment1,
            mock_comment2,
            mock_comment3,
        ]

        # Extract comments
        comments = self.scraper.extract_comments_with_retry(mock_submission)

        # Should filter out [deleted]
        assert len(comments) == 2
        assert mock_comment2 not in comments

    def test_extract_comments_with_retry_rate_limit(self):
        """Test comment extraction with rate limit retry."""
        mock_submission = Mock()
        mock_submission.title = "Daily Discussion"
        mock_submission.num_comments = 100

        # First call raises 429, second succeeds
        call_count = 0

        def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise Exception("429 Too Many Requests")
            return None

        mock_submission.comments.replace_more = Mock(side_effect=side_effect)
        mock_submission.comments.list.return_value = []

        # Should retry and eventually succeed
        with patch("time.sleep"):  # Don't actually sleep in tests
            _ = self.scraper.extract_comments_with_retry(mock_submission, max_retries=3)

        # Should have retried once
        assert call_count == 2

    def test_scrape_stats_dataclass(self):
        """Test ScrapeStats dataclass."""
        stats = ScrapeStats()
        assert stats.threads_processed == 0
        assert stats.total_comments == 0
        assert stats.new_comments == 0
        assert stats.articles_created == 0
        assert stats.ticker_links == 0
        assert stats.batches_saved == 0
        assert stats.rate_limit_events == 0
        assert stats.duration_ms == 0

    def test_scrape_stats_with_values(self):
        """Test ScrapeStats with values."""
        stats = ScrapeStats(
            threads_processed=3,
            total_comments=1000,
            new_comments=500,
            articles_created=500,
            ticker_links=1200,
            batches_saved=3,
            rate_limit_events=2,
            duration_ms=45000,
        )
        assert stats.threads_processed == 3
        assert stats.total_comments == 1000
        assert stats.new_comments == 500
        assert stats.articles_created == 500
        assert stats.ticker_links == 1200
        assert stats.batches_saved == 3
        assert stats.rate_limit_events == 2
        assert stats.duration_ms == 45000


class TestRedditScraperIntegration:
    """Integration tests for the scraper (require database)."""

    @pytest.mark.integration
    def test_get_scraping_status_empty(self):
        """Test getting status when no threads exist."""
        scraper = RedditScraper()

        # Initialize reddit
        from ingest.reddit_discussion_scraper import get_reddit_credentials

        try:
            client_id, client_secret, user_agent = get_reddit_credentials()
            scraper.initialize_reddit(client_id, client_secret, user_agent)

            status = scraper.get_scraping_status(
                "wallstreetbets", check_live_counts=False
            )

            assert "subreddit" in status
            assert status["subreddit"] == "wallstreetbets"
            assert "total_threads" in status
            assert "total_comments_scraped" in status
            assert "recent_threads" in status
        except ValueError:
            # Skip if no credentials
            pytest.skip("Reddit credentials not configured")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
