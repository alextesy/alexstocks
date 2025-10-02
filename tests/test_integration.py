"""Integration tests for the complete Reddit scraping and analysis pipeline."""

from datetime import UTC, datetime
from unittest.mock import Mock, patch

import pytest

from app.db.models import Article, ArticleTicker
from app.services.hybrid_sentiment import HybridSentimentService
from app.services.sentiment import SentimentService
from ingest.linker import TickerLinker
from ingest.reddit_discussion_scraper import RedditDiscussionScraper


@pytest.mark.skip(
    reason="Integration tests temporarily disabled - SQLite incompatibility"
)
@pytest.mark.integration
class TestRedditScrapingPipeline:
    """Test the complete Reddit scraping pipeline."""

    def test_full_reddit_scraping_pipeline(
        self, db_session, sample_tickers, mock_reddit_submission
    ):
        """Test the complete pipeline from Reddit scraping to database storage."""
        # Add tickers to database
        for ticker in sample_tickers:
            db_session.add(ticker)
        db_session.commit()

        # Mock Reddit parser
        parser = RedditDiscussionScraper()
        parser.reddit = Mock()

        # Mock subreddit and posts
        mock_subreddit = Mock()
        mock_subreddit.top.return_value = [mock_reddit_submission]
        parser.reddit.subreddit.return_value = mock_subreddit

        # Parse Reddit posts
        articles = parser.parse_subreddit_posts(
            "wallstreetbets", limit=1, time_filter="day"
        )

        assert len(articles) == 1
        article = articles[0]
        assert article.source == "reddit"
        assert article.subreddit == "wallstreetbets"

        # Add article to database
        db_session.add(article)
        db_session.flush()  # Get the ID

        # Test ticker linking
        with (
            patch("ingest.linker.get_content_scraper"),
            patch("ingest.linker.get_context_analyzer") as mock_context,
        ):

            mock_context.return_value.analyze_ticker_relevance.return_value = (
                0.8,
                ["Strong context"],
            )

            linker = TickerLinker(sample_tickers)
            ticker_links = linker.link_article(article, use_title_only=True)

            # Should find ticker mentions in the title
            assert len(ticker_links) > 0

            # Save ticker links to database
            for link in ticker_links:
                article_ticker = ArticleTicker(
                    article_id=article.id,
                    ticker=link.ticker,
                    confidence=link.confidence,
                    matched_terms=link.matched_terms,
                )
                db_session.add(article_ticker)

        db_session.commit()

        # Verify data in database
        saved_article = (
            db_session.query(Article).filter_by(reddit_id="test_submission_123").first()
        )
        assert saved_article is not None
        assert saved_article.title == "Test Reddit Post"

        # Check ticker links
        ticker_links = (
            db_session.query(ArticleTicker).filter_by(article_id=saved_article.id).all()
        )
        assert len(ticker_links) > 0

    def test_reddit_comment_processing_pipeline(
        self, db_session, sample_tickers, mock_reddit_comment
    ):
        """Test processing Reddit comments through the pipeline."""
        # Add tickers to database
        for ticker in sample_tickers:
            db_session.add(ticker)
        db_session.commit()

        # Create mock submission for the comment
        mock_submission = Mock()
        mock_submission.id = "test_submission"
        mock_submission.title = "Daily Discussion"
        mock_submission.subreddit = Mock()
        mock_submission.subreddit.display_name = "wallstreetbets"

        # Parse comment to article
        from ingest.reddit_discussion_scraper import RedditDiscussionScraper

        scraper = RedditDiscussionScraper()
        article = scraper.parse_comment_to_article(mock_reddit_comment, mock_submission)

        assert article.source == "reddit_comment"
        assert article.text == "This is a test comment about $AAPL stock"

        # Add to database
        db_session.add(article)
        db_session.flush()

        # Test ticker linking for comment
        with (
            patch("ingest.linker.get_content_scraper"),
            patch("ingest.linker.get_context_analyzer") as mock_context,
        ):

            mock_context.return_value.analyze_ticker_relevance.return_value = (
                0.9,
                ["Direct mention"],
            )

            linker = TickerLinker(sample_tickers)
            ticker_links = linker.link_article(article, use_title_only=True)

            # Should find AAPL mention
            assert len(ticker_links) > 0
            assert any(link.ticker == "AAPL" for link in ticker_links)

            # Save ticker links
            for link in ticker_links:
                article_ticker = ArticleTicker(
                    article_id=article.id,
                    ticker=link.ticker,
                    confidence=link.confidence,
                    matched_terms=link.matched_terms,
                )
                db_session.add(article_ticker)

        db_session.commit()

        # Verify comment processing
        saved_comment = (
            db_session.query(Article).filter_by(reddit_id="test_comment_456").first()
        )
        assert saved_comment is not None
        assert saved_comment.source == "reddit_comment"

        # Check ticker links
        ticker_links = (
            db_session.query(ArticleTicker).filter_by(article_id=saved_comment.id).all()
        )
        assert len(ticker_links) > 0
        assert any(link.ticker == "AAPL" for link in ticker_links)

    def test_sentiment_analysis_pipeline(self, db_session, sample_articles):
        """Test sentiment analysis pipeline."""
        # Add articles to database
        for article in sample_articles:
            db_session.add(article)
        db_session.commit()

        # Test sentiment analysis
        with patch(
            "app.services.sentiment.SentimentIntensityAnalyzer"
        ) as mock_analyzer_class:
            mock_analyzer = Mock()
            mock_analyzer.polarity_scores.return_value = {
                "pos": 0.8,
                "neu": 0.2,
                "neg": 0.0,
                "compound": 0.7,
            }
            mock_analyzer_class.return_value = mock_analyzer

            sentiment_service = SentimentService()

            # Analyze sentiment for each article
            for article in sample_articles:
                if article.source == "reddit_comment":
                    text = article.text
                else:
                    text = f"{article.title} {article.text}"

                sentiment_score = sentiment_service.analyze_sentiment(text)
                article.sentiment = sentiment_score

            db_session.commit()

            # Verify sentiment scores
            for article in sample_articles:
                assert article.sentiment == 0.7

    def test_hybrid_sentiment_analysis_pipeline(self, db_session, sample_articles):
        """Test hybrid sentiment analysis pipeline."""
        # Add articles to database
        for article in sample_articles:
            db_session.add(article)
        db_session.commit()

        # Test hybrid sentiment analysis
        with (
            patch(
                "app.services.hybrid_sentiment.get_llm_sentiment_service"
            ) as mock_llm,
            patch("app.services.hybrid_sentiment.get_sentiment_service") as mock_vader,
        ):

            mock_llm_service = Mock()
            mock_llm_service.analyze_sentiment.return_value = 0.8
            mock_llm.return_value = mock_llm_service

            mock_vader_service = Mock()
            mock_vader_service.analyze_sentiment.return_value = 0.6
            mock_vader.return_value = mock_vader_service

            hybrid_service = HybridSentimentService(dual_model_strategy=True)

            # Analyze sentiment for each article
            for article in sample_articles:
                if article.source == "reddit_comment":
                    text = article.text
                else:
                    text = f"{article.title} {article.text}"

                sentiment_score = hybrid_service.analyze_sentiment(text)
                article.sentiment = sentiment_score

            db_session.commit()

            # Verify sentiment scores (should use LLM since it's stronger)
            for article in sample_articles:
                assert article.sentiment == 0.8

    @pytest.mark.skip(
        reason="test_complete_reddit_ingestion_flow uses deprecated reddit.py - use test_reddit_scraper_new.py instead"
    )
    def test_complete_reddit_ingestion_flow(self, db_session, sample_tickers):
        """Test the complete Reddit ingestion flow."""
        # Add tickers to database
        for ticker in sample_tickers:
            db_session.add(ticker)
        db_session.commit()

        # Mock Reddit credentials
        with (
            patch("ingest.reddit.get_reddit_credentials") as mock_creds,
            patch("ingest.reddit.RedditParser") as mock_parser_class,
            patch("ingest.reddit.TickerLinker") as mock_linker_class,
            patch("ingest.reddit.upsert_reddit_article") as mock_upsert,
        ):

            mock_creds.return_value = ("client_id", "client_secret", "user_agent")

            # Mock parser
            mock_parser = Mock()
            mock_parser_class.return_value = mock_parser

            # Create test article
            test_article = Article(
                source="reddit",
                url="https://reddit.com/test",
                published_at=datetime.now(UTC),
                title="Test $AAPL post",
                text="This is a test post about Apple stock.",
                lang="en",
                reddit_id="test123",
                subreddit="test",
                author="testuser",
                upvotes=10,
                num_comments=5,
                reddit_url="https://reddit.com/test",
            )
            mock_parser.parse_multiple_subreddits.return_value = [test_article]

            # Mock linker
            mock_linker = Mock()
            mock_linker_class.return_value = mock_linker
            mock_linker.link_articles_to_db.return_value = [(test_article, [])]

            # Mock upsert
            mock_upsert.return_value = test_article

            # Run ingestion
            from ingest.reddit import ingest_reddit_data

            ingest_reddit_data(subreddits=["test"], limit_per_subreddit=1)

            # Verify calls
            mock_creds.assert_called_once()
            mock_parser.initialize_reddit.assert_called_once()
            mock_parser.parse_multiple_subreddits.assert_called_once()
            mock_linker.link_articles_to_db.assert_called_once()

    def test_ticker_linking_with_real_world_examples(self, db_session, sample_tickers):
        """Test ticker linking with realistic Reddit content."""
        # Add tickers to database
        for ticker in sample_tickers:
            db_session.add(ticker)
        db_session.commit()

        # Create realistic Reddit posts
        realistic_posts = [
            Article(
                source="reddit",
                url="https://reddit.com/r/wallstreetbets/comments/meme1/",
                published_at=datetime.now(UTC),
                title="🚀 $GME to the moon! 💎🙌 Diamond hands!",
                text="Just YOLO'd my life savings into $GME. This is not financial advice. $AMC is next!",
                lang="en",
                reddit_id="meme1",
                subreddit="wallstreetbets",
                author="diamond_hands_69",
                upvotes=2500,
                num_comments=150,
                reddit_url="https://reddit.com/r/wallstreetbets/comments/meme1/",
            ),
            Article(
                source="reddit_comment",
                url="https://reddit.com/r/investing/comments/tech1/comment1/",
                published_at=datetime.now(UTC),
                title="Comment",
                text="I'm bullish on $AAPL, $TSLA, and $NVDA. All three are great tech stocks for 2024.",
                lang="en",
                reddit_id="comment1",
                subreddit="investing",
                author="tech_investor",
                upvotes=25,
                num_comments=0,
                reddit_url="https://reddit.com/r/investing/comments/tech1/comment1/",
            ),
            Article(
                source="reddit",
                url="https://reddit.com/r/stocks/comments/analysis1/",
                published_at=datetime.now(UTC),
                title="Technical Analysis: SPY vs QQQ comparison",
                text="Looking at $SPY and $QQQ for my portfolio. Both are solid ETF choices. Also watching $MSFT earnings.",
                lang="en",
                reddit_id="analysis1",
                subreddit="stocks",
                author="chart_analyst",
                upvotes=75,
                num_comments=25,
                reddit_url="https://reddit.com/r/stocks/comments/analysis1/",
            ),
        ]

        # Add posts to database
        for post in realistic_posts:
            db_session.add(post)
        db_session.flush()

        # Test ticker linking
        with (
            patch("ingest.linker.get_content_scraper"),
            patch("ingest.linker.get_context_analyzer") as mock_context,
        ):

            mock_context.return_value.analyze_ticker_relevance.return_value = (
                0.8,
                ["Strong context"],
            )

            linker = TickerLinker(sample_tickers)

            total_links = 0
            for post in realistic_posts:
                ticker_links = linker.link_article(post, use_title_only=False)

                # Save ticker links
                for link in ticker_links:
                    article_ticker = ArticleTicker(
                        article_id=post.id,
                        ticker=link.ticker,
                        confidence=link.confidence,
                        matched_terms=link.matched_terms,
                    )
                    db_session.add(article_ticker)
                    total_links += 1

            db_session.commit()

            # Verify linking results
            assert total_links > 0

            # Check specific ticker links
            gme_links = db_session.query(ArticleTicker).filter_by(ticker="GME").all()
            assert len(gme_links) > 0

            aapl_links = db_session.query(ArticleTicker).filter_by(ticker="AAPL").all()
            assert len(aapl_links) > 0

            spy_links = db_session.query(ArticleTicker).filter_by(ticker="SPY").all()
            assert len(spy_links) > 0

    def test_sentiment_analysis_with_real_world_content(
        self, db_session, sample_articles
    ):
        """Test sentiment analysis with realistic Reddit content."""
        # Add articles to database
        for article in sample_articles:
            db_session.add(article)
        db_session.commit()

        # Test with different sentiment services
        with patch(
            "app.services.sentiment.SentimentIntensityAnalyzer"
        ) as mock_analyzer_class:
            mock_analyzer = Mock()
            mock_analyzer_class.return_value = mock_analyzer

            sentiment_service = SentimentService()

            # Test different sentiment scenarios
            sentiment_scenarios = [
                ("🚀 $GME to the moon! 💎🙌", {"compound": 0.8}),  # Very positive
                (
                    "This stock is terrible! Lost everything!",
                    {"compound": -0.7},
                ),  # Very negative
                ("The stock price is $100.", {"compound": 0.0}),  # Neutral
            ]

            for text, expected_scores in sentiment_scenarios:
                mock_analyzer.polarity_scores.return_value = expected_scores
                result = sentiment_service.analyze_sentiment(text)
                assert result == expected_scores["compound"]

    def test_error_handling_in_pipeline(self, db_session, sample_tickers):
        """Test error handling throughout the pipeline."""
        # Add tickers to database
        for ticker in sample_tickers:
            db_session.add(ticker)
        db_session.commit()

        # Test with invalid Reddit credentials
        with patch("ingest.reddit.get_reddit_credentials") as mock_creds:
            mock_creds.side_effect = ValueError("Invalid credentials")

            from ingest.reddit import ingest_reddit_data

            # Should not raise exception, just log error
            ingest_reddit_data()

        # Test with empty ticker list
        with patch("ingest.reddit.load_tickers", return_value=[]):
            from ingest.reddit import ingest_reddit_data

            # Should not raise exception, just log error
            ingest_reddit_data()

        # Test with malformed article data
        malformed_article = Article(
            source="reddit",
            url="",  # Empty URL
            published_at=datetime.now(UTC),
            title="",  # Empty title
            text="",  # Empty text
            lang="en",
            reddit_id="malformed",
            subreddit="test",
            author="testuser",
            upvotes=0,
            num_comments=0,
            reddit_url="",
        )

        db_session.add(malformed_article)
        db_session.flush()

        # Test ticker linking with malformed data
        with (
            patch("ingest.linker.get_content_scraper"),
            patch("ingest.linker.get_context_analyzer"),
        ):

            linker = TickerLinker(sample_tickers)
            ticker_links = linker.link_article(malformed_article, use_title_only=True)

            # Should return empty list for malformed data
            assert len(ticker_links) == 0

    def test_database_transaction_rollback(self, db_session, sample_tickers):
        """Test database transaction rollback on errors."""
        # Add tickers to database
        for ticker in sample_tickers:
            db_session.add(ticker)
        db_session.commit()

        # Create article that will cause an error
        article = Article(
            source="reddit",
            url="https://reddit.com/test",
            published_at=datetime.now(UTC),
            title="Test post",
            text="Test content",
            lang="en",
            reddit_id="test123",
            subreddit="test",
            author="testuser",
            upvotes=10,
            num_comments=5,
            reddit_url="https://reddit.com/test",
        )

        db_session.add(article)
        db_session.flush()

        # Simulate an error during ticker linking
        with (
            patch("ingest.linker.get_content_scraper"),
            patch("ingest.linker.get_context_analyzer") as mock_context,
        ):

            mock_context.return_value.analyze_ticker_relevance.side_effect = Exception(
                "Linking error"
            )

            linker = TickerLinker(sample_tickers)

            # This should handle the error gracefully
            ticker_links = linker.link_article(article, use_title_only=True)
            assert len(ticker_links) == 0

        # Verify article is still in database
        saved_article = db_session.query(Article).filter_by(reddit_id="test123").first()
        assert saved_article is not None
