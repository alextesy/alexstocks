"""Tests for Reddit scraping functionality."""

from datetime import UTC, datetime
from unittest.mock import Mock, patch

import pytest
from faker import Faker

from ingest.reddit import get_reddit_credentials, ingest_reddit_data
from ingest.reddit_discussion_scraper import RedditDiscussionScraper
from ingest.reddit_full_scraper import RedditFullScraper
from ingest.reddit_incremental_scraper import RedditIncrementalScraper
from ingest.reddit_parser import RedditParser

fake = Faker()


class TestRedditParser:
    """Test Reddit post parsing functionality."""

    def setup_method(self):
        """Set up test fixtures."""
        self.parser = RedditParser()
        self.mock_reddit = Mock()
        self.parser.reddit = self.mock_reddit

    def test_initialize_reddit(self):
        """Test Reddit client initialization."""
        client_id = "test_client_id"
        client_secret = "test_client_secret"
        user_agent = "test_user_agent"

        with patch("praw.Reddit") as mock_praw:
            self.parser.initialize_reddit(client_id, client_secret, user_agent)

            mock_praw.assert_called_once_with(
                client_id=client_id, client_secret=client_secret, user_agent=user_agent
            )

    def test_parse_submission(self):
        """Test parsing a Reddit submission into Article model."""
        # Create mock submission
        mock_submission = Mock()
        mock_submission.id = "test123"
        mock_submission.title = "Test Post Title"
        mock_submission.selftext = "Test post content"
        mock_submission.permalink = "/r/wallstreetbets/comments/test123/"
        mock_submission.created_utc = 1640995200  # 2022-01-01 00:00:00 UTC
        mock_submission.author = Mock()
        mock_submission.author.name = "testuser"
        mock_submission.score = 100
        mock_submission.num_comments = 50

        subreddit_name = "wallstreetbets"

        # Parse submission
        article = self.parser.parse_submission(mock_submission, subreddit_name)

        # Assertions
        assert article.source == "reddit"
        assert article.title == "Test Post Title"
        assert article.text == "Test Post Title\n\nTest post content"
        assert article.reddit_id == "test123"
        assert article.subreddit == "wallstreetbets"
        assert article.author == "testuser"
        assert article.upvotes == 100
        assert article.num_comments == 50
        assert article.url == "https://reddit.com/r/wallstreetbets/comments/test123/"
        assert (
            article.reddit_url
            == "https://reddit.com/r/wallstreetbets/comments/test123/"
        )
        assert article.published_at == datetime(2022, 1, 1, 0, 0, 0, tzinfo=UTC)

    def test_parse_submission_no_selftext(self):
        """Test parsing submission with only title."""
        mock_submission = Mock()
        mock_submission.id = "test456"
        mock_submission.title = "Title Only Post"
        mock_submission.selftext = ""
        mock_submission.permalink = "/r/investing/comments/test456/"
        mock_submission.created_utc = 1640995200
        mock_submission.author = Mock()
        mock_submission.author.name = "investor"
        mock_submission.score = 25
        mock_submission.num_comments = 10

        article = self.parser.parse_submission(mock_submission, "investing")

        assert article.title == "Title Only Post"
        assert article.text == "Title Only Post"
        assert article.subreddit == "investing"

    def test_parse_submission_no_author(self):
        """Test parsing submission with deleted author."""
        mock_submission = Mock()
        mock_submission.id = "test789"
        mock_submission.title = "Deleted Author Post"
        mock_submission.selftext = "Content"
        mock_submission.permalink = "/r/stocks/comments/test789/"
        mock_submission.created_utc = 1640995200
        mock_submission.author = None
        mock_submission.score = 5
        mock_submission.num_comments = 2

        article = self.parser.parse_submission(mock_submission, "stocks")

        assert article.author is None
        assert article.title == "Deleted Author Post"

    def test_fetch_subreddit_posts(self):
        """Test fetching posts from subreddit."""
        # Mock subreddit and posts
        mock_subreddit = Mock()
        mock_posts = [Mock(), Mock(), Mock()]
        mock_subreddit.top.return_value = mock_posts
        self.mock_reddit.subreddit.return_value = mock_subreddit

        posts = self.parser.fetch_subreddit_posts(
            "wallstreetbets", limit=50, time_filter="day"
        )

        assert len(posts) == 3
        self.mock_reddit.subreddit.assert_called_once_with("wallstreetbets")
        mock_subreddit.top.assert_called_once_with(time_filter="day", limit=50)

    def test_fetch_subreddit_posts_not_initialized(self):
        """Test fetching posts without initializing Reddit client."""
        parser = RedditParser()  # No reddit client

        with pytest.raises(ValueError, match="Reddit client not initialized"):
            parser.fetch_subreddit_posts("wallstreetbets")

    def test_fetch_subreddit_posts_error(self):
        """Test error handling when fetching posts fails."""
        self.mock_reddit.subreddit.side_effect = Exception("API Error")

        posts = self.parser.fetch_subreddit_posts("wallstreetbets")

        assert posts == []

    def test_parse_subreddit_posts(self):
        """Test parsing posts from subreddit."""
        # Mock submissions
        mock_submission1 = Mock()
        mock_submission1.id = "post1"
        mock_submission1.title = "Post 1"
        mock_submission1.selftext = "Content 1"
        mock_submission1.permalink = "/r/test/comments/post1/"
        mock_submission1.created_utc = 1640995200
        mock_submission1.author = Mock()
        mock_submission1.author.name = "user1"
        mock_submission1.score = 10
        mock_submission1.num_comments = 5

        mock_submission2 = Mock()
        mock_submission2.id = "post2"
        mock_submission2.title = "Post 2"
        mock_submission2.selftext = ""
        mock_submission2.permalink = "/r/test/comments/post2/"
        mock_submission2.created_utc = 1640995200
        mock_submission2.author = None
        mock_submission2.score = 20
        mock_submission2.num_comments = 10

        # Mock subreddit
        mock_subreddit = Mock()
        mock_subreddit.top.return_value = [mock_submission1, mock_submission2]
        self.mock_reddit.subreddit.return_value = mock_subreddit

        articles = self.parser.parse_subreddit_posts(
            "test", limit=10, time_filter="week"
        )

        assert len(articles) == 2
        assert articles[0].title == "Post 1"
        assert articles[1].title == "Post 2"

    def test_parse_multiple_subreddits(self):
        """Test parsing posts from multiple subreddits."""
        # Create proper mock submissions
        mock_submission1 = Mock()
        mock_submission1.id = "post1"
        mock_submission1.title = "Post 1"
        mock_submission1.selftext = "Content 1"
        mock_submission1.permalink = "/r/wallstreetbets/comments/post1/"
        mock_submission1.created_utc = 1640995200
        mock_submission1.author = Mock()
        mock_submission1.author.name = "user1"
        mock_submission1.score = 10
        mock_submission1.num_comments = 5

        mock_submission2 = Mock()
        mock_submission2.id = "post2"
        mock_submission2.title = "Post 2"
        mock_submission2.selftext = "Content 2"
        mock_submission2.permalink = "/r/investing/comments/post2/"
        mock_submission2.created_utc = 1640995200
        mock_submission2.author = Mock()
        mock_submission2.author.name = "user2"
        mock_submission2.score = 20
        mock_submission2.num_comments = 10

        mock_submission3 = Mock()
        mock_submission3.id = "post3"
        mock_submission3.title = "Post 3"
        mock_submission3.selftext = "Content 3"
        mock_submission3.permalink = "/r/investing/comments/post3/"
        mock_submission3.created_utc = 1640995200
        mock_submission3.author = Mock()
        mock_submission3.author.name = "user3"
        mock_submission3.score = 30
        mock_submission3.num_comments = 15

        # Mock subreddit responses
        mock_subreddit1 = Mock()
        mock_subreddit1.top.return_value = [mock_submission1]
        mock_subreddit2 = Mock()
        mock_subreddit2.top.return_value = [mock_submission2, mock_submission3]

        self.mock_reddit.subreddit.side_effect = [mock_subreddit1, mock_subreddit2]

        articles = self.parser.parse_multiple_subreddits(
            ["wallstreetbets", "investing"], limit_per_subreddit=5, time_filter="day"
        )

        assert len(articles) == 3  # 1 + 2
        assert self.mock_reddit.subreddit.call_count == 2


class TestRedditDiscussionScraper:
    """Test Reddit discussion thread scraping."""

    def setup_method(self):
        """Set up test fixtures."""
        self.scraper = RedditDiscussionScraper()

    def test_initialize_reddit(self):
        """Test Reddit client initialization."""
        client_id = "test_client_id"
        client_secret = "test_client_secret"
        user_agent = "test_user_agent"

        with patch("praw.Reddit") as mock_praw:
            self.scraper.initialize_reddit(client_id, client_secret, user_agent)

            mock_praw.assert_called_once_with(
                client_id=client_id,
                client_secret=client_secret,
                user_agent=user_agent,
            )

    def test_initialize_reddit_error(self):
        """Test error handling during Reddit initialization."""
        with patch("praw.Reddit", side_effect=Exception("Connection failed")):
            with pytest.raises(Exception, match="Connection failed"):
                self.scraper.initialize_reddit("id", "secret", "agent")

    def test_find_daily_discussion_threads(self):
        """Test finding daily discussion threads."""
        # Mock Reddit client and subreddit
        mock_reddit = Mock()
        mock_subreddit = Mock()

        # Create proper mock submissions with titles that match the filter criteria
        mock_submission1 = Mock()
        mock_submission1.id = "thread1"
        mock_submission1.title = "Daily Discussion Thread"
        mock_submission2 = Mock()
        mock_submission2.id = "thread2"
        mock_submission2.title = "Weekend Discussion Thread"

        mock_submissions = [mock_submission1, mock_submission2]

        # Mock the hot and top methods that the actual implementation uses
        mock_subreddit.hot.return_value = mock_submissions
        mock_subreddit.top.return_value = []  # No additional posts from top
        mock_reddit.subreddit.return_value = mock_subreddit
        self.scraper.reddit = mock_reddit

        threads = self.scraper.find_daily_discussion_threads("wallstreetbets", limit=10)

        assert len(threads) == 2
        mock_reddit.subreddit.assert_called_once_with("wallstreetbets")
        mock_subreddit.hot.assert_called_once_with(limit=10)

    def test_parse_comment_to_article(self):
        """Test parsing Reddit comment to Article model."""
        # Mock comment and submission
        mock_comment = Mock()
        mock_comment.id = "comment123"
        mock_comment.body = "This is a test comment about $AAPL"
        mock_comment.created_utc = 1640995200
        mock_comment.author = Mock()
        mock_comment.author.name = "commenter"
        mock_comment.score = 5
        mock_comment.permalink = "/r/wallstreetbets/comments/post123/comment123/"
        mock_comment.subreddit = Mock()
        mock_comment.subreddit.display_name = "wallstreetbets"

        mock_submission = Mock()
        mock_submission.id = "post123"
        mock_submission.title = "Daily Discussion"
        mock_submission.subreddit = Mock()
        mock_submission.subreddit.display_name = "wallstreetbets"

        article = self.scraper.parse_comment_to_article(mock_comment, mock_submission)

        assert article.source == "reddit_comment"
        assert article.text == "This is a test comment about $AAPL"
        assert article.reddit_id == "comment123"
        assert article.author == "commenter"
        assert article.upvotes == 5
        assert article.subreddit == "wallstreetbets"
        assert article.published_at == datetime(2022, 1, 1, 0, 0, 0, tzinfo=UTC)


class TestRedditFullScraper:
    """Test full Reddit thread scraping."""

    def setup_method(self):
        """Set up test fixtures."""
        self.scraper = RedditFullScraper(max_scraping_workers=3)

    def test_initialize_reddit(self):
        """Test Reddit client initialization."""
        client_id = "test_client_id"
        client_secret = "test_client_secret"
        user_agent = "test_user_agent"

        with patch.object(
            self.scraper.discussion_scraper, "initialize_reddit"
        ) as mock_init:
            self.scraper.initialize_reddit(client_id, client_secret, user_agent)
            mock_init.assert_called_once_with(client_id, client_secret, user_agent)

    def test_extract_all_comments_from_thread(self):
        """Test extracting all comments from a thread."""
        # Initialize the scraper's Reddit instance
        self.scraper.reddit = Mock()

        # Mock submission with comments
        mock_submission = Mock()
        mock_comment1 = Mock()
        mock_comment1.id = "comment1"
        mock_comment1.body = "First comment"
        mock_comment1.replies = []

        mock_comment2 = Mock()
        mock_comment2.id = "comment2"
        mock_comment2.body = "Second comment"
        mock_comment2.replies = []

        mock_submission.comments.list.return_value = [mock_comment1, mock_comment2]

        comments = self.scraper.extract_all_comments_from_thread(mock_submission)

        assert len(comments) == 2
        assert comments[0].id == "comment1"
        assert comments[1].id == "comment2"


class TestRedditIncrementalScraper:
    """Test incremental Reddit scraping."""

    def setup_method(self):
        """Set up test fixtures."""
        self.scraper = RedditIncrementalScraper()

    def test_initialize_reddit(self):
        """Test Reddit client initialization."""
        client_id = "test_client_id"
        client_secret = "test_client_secret"
        user_agent = "test_user_agent"

        with patch.object(
            self.scraper.discussion_scraper, "initialize_reddit"
        ) as mock_init:
            self.scraper.initialize_reddit(client_id, client_secret, user_agent)
            mock_init.assert_called_once_with(client_id, client_secret, user_agent)


class TestRedditIngestion:
    """Test Reddit data ingestion pipeline."""

    @patch("ingest.reddit.SessionLocal")
    @patch("ingest.reddit.get_reddit_credentials")
    @patch("ingest.reddit.RedditParser")
    @patch("ingest.reddit.TickerLinker")
    def test_ingest_reddit_data_success(
        self, mock_linker_class, mock_parser_class, mock_credentials, mock_session_local
    ):
        """Test successful Reddit data ingestion."""
        # Mock credentials
        mock_credentials.return_value = ("client_id", "client_secret", "user_agent")

        # Mock database session
        mock_db = Mock()
        mock_session_local.return_value = mock_db

        # Mock tickers
        mock_ticker = Mock()
        mock_ticker.symbol = "AAPL"
        mock_db.execute.return_value.scalars.return_value.all.return_value = [
            mock_ticker
        ]

        # Mock parser
        mock_parser = Mock()
        mock_parser_class.return_value = mock_parser
        mock_article = Mock()
        mock_article.url = "https://reddit.com/test"
        mock_parser.parse_multiple_subreddits.return_value = [mock_article]

        # Mock linker
        mock_linker = Mock()
        mock_linker_class.return_value = mock_linker
        mock_linker.link_articles_to_db.return_value = [(mock_article, [])]

        # Mock upsert function
        with patch("ingest.reddit.upsert_reddit_article", return_value=mock_article):
            ingest_reddit_data(subreddits=["wallstreetbets"], limit_per_subreddit=10)

        # Verify calls
        mock_credentials.assert_called_once()
        mock_parser.initialize_reddit.assert_called_once_with(
            "client_id", "client_secret", "user_agent"
        )
        mock_parser.parse_multiple_subreddits.assert_called_once_with(
            ["wallstreetbets"], 10, "day"
        )
        mock_linker.link_articles_to_db.assert_called_once_with([mock_article])

    @patch("ingest.reddit.get_reddit_credentials")
    def test_ingest_reddit_data_credentials_error(self, mock_credentials):
        """Test ingestion with invalid credentials."""
        mock_credentials.side_effect = ValueError("Invalid credentials")

        # Should not raise exception, just log error
        ingest_reddit_data()

    @patch("ingest.reddit.SessionLocal")
    @patch("ingest.reddit.get_reddit_credentials")
    def test_ingest_reddit_data_no_tickers(self, mock_credentials, mock_session_local):
        """Test ingestion when no tickers are found."""
        mock_credentials.return_value = ("client_id", "client_secret", "user_agent")
        mock_db = Mock()
        mock_session_local.return_value = mock_db
        mock_db.execute.return_value.scalars.return_value.all.return_value = []

        # Should not raise exception, just log error
        ingest_reddit_data()

    @patch("ingest.reddit.get_reddit_credentials")
    def test_get_reddit_credentials(self, mock_credentials):
        """Test getting Reddit credentials from environment."""
        mock_credentials.return_value = (
            "test_client_id",
            "test_client_secret",
            "test_user_agent",
        )

        client_id, client_secret, user_agent = get_reddit_credentials()

        assert client_id == "test_client_id"
        assert client_secret == "test_client_secret"
        assert user_agent == "test_user_agent"


class TestRedditScrapingIntegration:
    """Integration tests for Reddit scraping with real-world examples."""

    def test_reddit_parser_with_real_world_data(self):
        """Test Reddit parser with realistic data structures."""
        parser = RedditParser()

        # Create realistic mock submission
        mock_submission = Mock()
        mock_submission.id = "abc123"
        mock_submission.title = "🚀 $GME to the moon! Diamond hands! 💎🙌"
        mock_submission.selftext = (
            "Just bought more shares. This is not financial advice."
        )
        mock_submission.permalink = "/r/wallstreetbets/comments/abc123/gme_to_the_moon/"
        mock_submission.created_utc = 1640995200
        mock_submission.author = Mock()
        mock_submission.author.name = "diamond_hands_69"
        mock_submission.score = 1250
        mock_submission.num_comments = 89

        article = parser.parse_submission(mock_submission, "wallstreetbets")

        # Verify realistic data handling
        assert "🚀" in article.title
        assert "$GME" in article.title
        assert "diamond_hands_69" == article.author
        assert article.upvotes == 1250
        assert article.num_comments == 89
        assert "wallstreetbets" in article.url

    def test_comment_parsing_with_ticker_mentions(self):
        """Test comment parsing with various ticker mention formats."""
        scraper = RedditDiscussionScraper()

        # Mock comment with various ticker formats
        mock_comment = Mock()
        mock_comment.id = "comment456"
        mock_comment.body = (
            "I'm bullish on $AAPL, $TSLA, and NVDA. Also watching SPY and QQQ."
        )
        mock_comment.created_utc = 1640995200
        mock_comment.author = Mock()
        mock_comment.author.name = "trader_pro"
        mock_comment.score = 15
        mock_comment.permalink = "/r/investing/comments/post456/comment456/"

        mock_submission = Mock()
        mock_submission.id = "post456"
        mock_submission.title = "Weekly Discussion Thread"
        mock_submission.subreddit = Mock()
        mock_submission.subreddit.display_name = "investing"

        article = scraper.parse_comment_to_article(mock_comment, mock_submission)

        # Verify ticker mentions are preserved
        assert "$AAPL" in article.text
        assert "$TSLA" in article.text
        assert "NVDA" in article.text
        assert "SPY" in article.text
        assert "QQQ" in article.text
        assert article.source == "reddit_comment"

    def test_reddit_url_generation(self):
        """Test proper Reddit URL generation."""
        parser = RedditParser()

        mock_submission = Mock()
        mock_submission.id = "test789"
        mock_submission.title = "Test Post"
        mock_submission.selftext = ""
        mock_submission.permalink = "/r/stocks/comments/test789/test_post/"
        mock_submission.created_utc = 1640995200
        mock_submission.author = Mock()
        mock_submission.author.name = "testuser"
        mock_submission.score = 1
        mock_submission.num_comments = 0

        article = parser.parse_submission(mock_submission, "stocks")

        expected_url = "https://reddit.com/r/stocks/comments/test789/test_post/"
        assert article.url == expected_url
        assert article.reddit_url == expected_url

    def test_handling_deleted_removed_content(self):
        """Test handling of deleted/removed Reddit content."""
        parser = RedditParser()

        # Test deleted post
        mock_submission = Mock()
        mock_submission.id = "deleted123"
        mock_submission.title = "[deleted]"
        mock_submission.selftext = "[removed]"
        mock_submission.permalink = "/r/wallstreetbets/comments/deleted123/"
        mock_submission.created_utc = 1640995200
        mock_submission.author = None
        mock_submission.score = 0
        mock_submission.num_comments = 0

        article = parser.parse_submission(mock_submission, "wallstreetbets")

        assert article.title == "[deleted]"
        assert article.text == "[deleted]\n\n[removed]"
        assert article.author is None
        assert article.upvotes == 0

    def test_unicode_emoji_handling(self):
        """Test proper handling of Unicode characters and emojis."""
        parser = RedditParser()

        mock_submission = Mock()
        mock_submission.id = "emoji123"
        mock_submission.title = "📈 $NVDA earnings beat! 🎉🚀💎🙌"
        mock_submission.selftext = "This is amazing! 🚀🚀🚀"
        mock_submission.permalink = "/r/wallstreetbets/comments/emoji123/"
        mock_submission.created_utc = 1640995200
        mock_submission.author = Mock()
        mock_submission.author.name = "moon_boi"
        mock_submission.score = 500
        mock_submission.num_comments = 25

        article = parser.parse_submission(mock_submission, "wallstreetbets")

        # Verify Unicode characters are preserved
        assert "📈" in article.title
        assert "🎉" in article.title
        assert "🚀" in article.text
        assert "💎" in article.title
        assert "🙌" in article.title
