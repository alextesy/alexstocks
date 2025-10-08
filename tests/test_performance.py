"""Performance tests for the Reddit scraping and analysis pipeline."""

import time
from datetime import UTC, datetime
from unittest.mock import Mock, patch

import pytest

from app.db.models import Article, ArticleTicker
from app.services.hybrid_sentiment import HybridSentimentService
from app.services.sentiment import SentimentService
from jobs.ingest.linker import TickerLinker
from jobs.ingest.reddit_discussion_scraper import RedditDiscussionScraper


@pytest.mark.performance
class TestPerformance:
    """Performance tests for the pipeline components."""

    @pytest.mark.skip(
        reason="test_reddit_parser_performance tests deleted parse_subreddit_posts method"
    )
    def test_reddit_parser_performance(self, sample_tickers):
        """Test Reddit parser performance with large datasets."""
        parser = RedditDiscussionScraper()
        parser.reddit = Mock()

        # Create mock submissions
        mock_submissions = []
        for i in range(100):  # Test with 100 posts
            submission = Mock()
            submission.id = f"post_{i}"
            submission.title = f"Test Post {i} about $AAPL and $TSLA"
            submission.selftext = f"This is test content {i} with ticker mentions."
            submission.permalink = f"/r/test/comments/post_{i}/"
            submission.created_utc = 1640995200 + i
            submission.author = Mock()
            submission.author.name = f"user_{i}"
            submission.score = i * 10
            submission.num_comments = i * 5
            mock_submissions.append(submission)

        # Mock subreddit
        mock_subreddit = Mock()
        mock_subreddit.top.return_value = mock_submissions
        parser.reddit.subreddit.return_value = mock_subreddit

        # Measure parsing time
        start_time = time.time()
        articles = parser.parse_subreddit_posts("test", limit=100, time_filter="day")  # type: ignore[attr-defined]
        end_time = time.time()

        parsing_time = end_time - start_time

        # Verify results
        assert len(articles) == 100
        assert parsing_time < 5.0  # Should parse 100 posts in under 5 seconds

        print(f"Parsed {len(articles)} articles in {parsing_time:.2f} seconds")
        print(f"Average time per article: {parsing_time/len(articles)*1000:.2f} ms")

    def test_ticker_linking_performance(self, sample_tickers):
        """Test ticker linking performance with large datasets."""
        # Create test articles
        articles = []
        for i in range(50):  # Test with 50 articles
            article = Article(
                source="reddit",
                url=f"https://reddit.com/test_{i}",
                published_at=datetime.now(UTC),
                title=f"Test Post {i} about $AAPL, $TSLA, and $NVDA",
                text=f"This is test content {i} with multiple ticker mentions like $GME, $AMC, and $SPY.",
                lang="en",
                reddit_id=f"test_{i}",
                subreddit="test",
                author=f"user_{i}",
                upvotes=i * 10,
                num_comments=i * 5,
                reddit_url=f"https://reddit.com/test_{i}",
            )
            articles.append(article)

        # Test ticker linking performance
        with (
            patch("ingest.linker.get_content_scraper"),
            patch("ingest.linker.get_context_analyzer") as mock_context,
        ):

            mock_context.return_value.analyze_ticker_relevance.return_value = (
                0.8,
                ["Strong context"],
            )

            linker = TickerLinker(sample_tickers)

            start_time = time.time()
            total_links = 0

            for article in articles:
                ticker_links = linker.link_article(article, use_title_only=True)
                total_links += len(ticker_links)

            end_time = time.time()
            linking_time = end_time - start_time

            # Verify results
            assert total_links > 0
            assert linking_time < 10.0  # Should link 50 articles in under 10 seconds

            print(f"Linked {total_links} ticker mentions in {linking_time:.2f} seconds")
            print(f"Average time per article: {linking_time/len(articles)*1000:.2f} ms")
            print(f"Average links per article: {total_links/len(articles):.2f}")

    def test_sentiment_analysis_performance(self):
        """Test sentiment analysis performance with large datasets."""
        # Create test texts
        test_texts = []
        for i in range(100):  # Test with 100 texts
            text = f"This is test text {i} about stocks. I love $AAPL and $TSLA! The market is great!"
            test_texts.append(text)

        # Test VADER sentiment performance
        with patch(
            "app.services.sentiment.SentimentIntensityAnalyzer"
        ) as mock_analyzer_class:
            mock_analyzer = Mock()
            mock_analyzer.polarity_scores.return_value = {
                "pos": 0.6,
                "neu": 0.3,
                "neg": 0.1,
                "compound": 0.5,
            }
            mock_analyzer_class.return_value = mock_analyzer

            sentiment_service = SentimentService()

            start_time = time.time()
            results = []

            for text in test_texts:
                score = sentiment_service.analyze_sentiment(text)
                results.append(score)

            end_time = time.time()
            analysis_time = end_time - start_time

            # Verify results
            assert len(results) == 100
            assert all(score == 0.5 for score in results)
            assert analysis_time < 5.0  # Should analyze 100 texts in under 5 seconds

            print(f"Analyzed {len(results)} texts in {analysis_time:.2f} seconds")
            print(f"Average time per text: {analysis_time/len(results)*1000:.2f} ms")

    def test_hybrid_sentiment_performance(self):
        """Test hybrid sentiment analysis performance."""
        # Create test texts
        test_texts = []
        for i in range(20):  # Test with 20 texts (LLM is slower)
            text = f"This is test text {i} about financial markets. $AAPL is performing well!"
            test_texts.append(text)

        # Test hybrid sentiment performance
        with (
            patch(
                "app.services.hybrid_sentiment.get_llm_sentiment_service"
            ) as mock_llm,
            patch("app.services.hybrid_sentiment.get_sentiment_service") as mock_vader,
        ):

            mock_llm_service = Mock()
            mock_llm_service.analyze_sentiment.return_value = 0.7
            mock_llm.return_value = mock_llm_service

            mock_vader_service = Mock()
            mock_vader_service.analyze_sentiment.return_value = 0.5
            mock_vader.return_value = mock_vader_service

            hybrid_service = HybridSentimentService(dual_model_strategy=True)

            start_time = time.time()
            results = []

            for text in test_texts:
                score = hybrid_service.analyze_sentiment(text)
                results.append(score)

            end_time = time.time()
            analysis_time = end_time - start_time

            # Verify results
            assert len(results) == 20
            assert all(
                score == 0.7 for score in results
            )  # Should use LLM since it's stronger
            assert analysis_time < 30.0  # Should analyze 20 texts in under 30 seconds

            print(
                f"Analyzed {len(results)} texts with hybrid service in {analysis_time:.2f} seconds"
            )
            print(f"Average time per text: {analysis_time/len(results)*1000:.2f} ms")

    @pytest.mark.skip(
        reason="DB performance test temporarily disabled - SQLite incompatibility"
    )
    def test_database_operations_performance(self, db_session, sample_tickers):
        """Test database operations performance."""
        # Add tickers to database
        for ticker in sample_tickers:
            db_session.add(ticker)
        db_session.commit()

        # Create test articles
        articles = []
        for i in range(100):  # Test with 100 articles
            article = Article(
                source="reddit",
                url=f"https://reddit.com/test_{i}",
                published_at=datetime.now(UTC),
                title=f"Test Post {i}",
                text=f"Test content {i}",
                lang="en",
                reddit_id=f"test_{i}",
                subreddit="test",
                author=f"user_{i}",
                upvotes=i * 10,
                num_comments=i * 5,
                reddit_url=f"https://reddit.com/test_{i}",
            )
            articles.append(article)

        # Test bulk insert performance
        start_time = time.time()

        for article in articles:
            db_session.add(article)

        db_session.flush()  # Get IDs

        # Add ticker links
        for article in articles:
            for ticker in sample_tickers[:3]:  # Link to first 3 tickers
                article_ticker = ArticleTicker(
                    article_id=article.id,
                    ticker=ticker.symbol,
                    confidence=0.8,
                    matched_terms=[f"${ticker.symbol}"],
                )
                db_session.add(article_ticker)

        db_session.commit()

        end_time = time.time()
        db_time = end_time - start_time

        # Verify results
        assert (
            db_time < 5.0
        )  # Should insert 100 articles + 300 ticker links in under 5 seconds

        # Verify data in database
        article_count = db_session.query(Article).count()
        ticker_link_count = db_session.query(ArticleTicker).count()

        assert article_count == 100
        assert ticker_link_count == 300

        print(
            f"Inserted {article_count} articles and {ticker_link_count} ticker links in {db_time:.2f} seconds"
        )
        print(f"Average time per article: {db_time/article_count*1000:.2f} ms")

    def test_memory_usage_performance(self, sample_tickers):
        """Test memory usage with large datasets."""
        import os

        import psutil

        # Get initial memory usage
        process = psutil.Process(os.getpid())
        initial_memory = process.memory_info().rss / 1024 / 1024  # MB

        # Create large dataset
        articles = []
        for i in range(1000):  # Test with 1000 articles
            article = Article(
                source="reddit",
                url=f"https://reddit.com/test_{i}",
                published_at=datetime.now(UTC),
                title=f"Test Post {i} about $AAPL, $TSLA, $NVDA, $GME, $AMC",
                text=f"This is test content {i} with multiple ticker mentions and some additional text to make it longer.",
                lang="en",
                reddit_id=f"test_{i}",
                subreddit="test",
                author=f"user_{i}",
                upvotes=i * 10,
                num_comments=i * 5,
                reddit_url=f"https://reddit.com/test_{i}",
            )
            articles.append(article)

        # Get memory after creating articles
        after_articles_memory = process.memory_info().rss / 1024 / 1024  # MB

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

            ticker_links = []
            for article in articles:
                links = linker.link_article(article, use_title_only=True)
                ticker_links.extend(links)

            # Get memory after ticker linking
            after_linking_memory = process.memory_info().rss / 1024 / 1024  # MB

            # Calculate memory usage
            articles_memory = after_articles_memory - initial_memory
            linking_memory = after_linking_memory - after_articles_memory
            total_memory = after_linking_memory - initial_memory

            # Verify memory usage is reasonable
            assert total_memory < 500  # Should use less than 500MB for 1000 articles

            print("Memory usage:")
            print(f"  Initial: {initial_memory:.2f} MB")
            print(
                f"  After articles: {after_articles_memory:.2f} MB (+{articles_memory:.2f} MB)"
            )
            print(
                f"  After linking: {after_linking_memory:.2f} MB (+{linking_memory:.2f} MB)"
            )
            print(f"  Total increase: {total_memory:.2f} MB")
            print(f"  Memory per article: {total_memory/len(articles)*1024:.2f} KB")

    @pytest.mark.skip(reason="Flaky timing-based test - temporarily disabled")
    def test_concurrent_processing_performance(self, sample_tickers):
        """Test concurrent processing performance."""
        import concurrent.futures

        # Create test articles
        articles = []
        for i in range(50):  # Test with 50 articles
            article = Article(
                source="reddit",
                url=f"https://reddit.com/test_{i}",
                published_at=datetime.now(UTC),
                title=f"Test Post {i} about $AAPL and $TSLA",
                text=f"This is test content {i} with ticker mentions.",
                lang="en",
                reddit_id=f"test_{i}",
                subreddit="test",
                author=f"user_{i}",
                upvotes=i * 10,
                num_comments=i * 5,
                reddit_url=f"https://reddit.com/test_{i}",
            )
            articles.append(article)

        # Test sequential processing
        with (
            patch("ingest.linker.get_content_scraper"),
            patch("ingest.linker.get_context_analyzer") as mock_context,
        ):

            mock_context.return_value.analyze_ticker_relevance.return_value = (
                0.8,
                ["Strong context"],
            )

            linker = TickerLinker(sample_tickers)

            start_time = time.time()
            sequential_results = []

            for article in articles:
                links = linker.link_article(article, use_title_only=True)
                sequential_results.extend(links)

            sequential_time = time.time() - start_time

            # Test concurrent processing
            start_time = time.time()
            concurrent_results = []

            def process_article(article):
                return linker.link_article(article, use_title_only=True)

            with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
                future_to_article = {
                    executor.submit(process_article, article): article
                    for article in articles
                }

                for future in concurrent.futures.as_completed(future_to_article):
                    links = future.result()
                    concurrent_results.extend(links)

            concurrent_time = time.time() - start_time

            # Verify results
            assert len(sequential_results) == len(concurrent_results)

            print(f"Sequential processing: {sequential_time:.2f} seconds")
            print(f"Concurrent processing: {concurrent_time:.2f} seconds")
            print(f"Speedup: {sequential_time/concurrent_time:.2f}x")

            # Concurrent processing should be faster (though not always due to GIL)
            # Just verify it completes successfully
            assert (
                concurrent_time < sequential_time * 2
            )  # Should not be more than 2x slower

    def test_large_text_processing_performance(self):
        """Test performance with large text inputs."""
        # Create large text
        large_text = (
            "This is a test about $AAPL, $TSLA, $NVDA, $GME, $AMC, $SPY, $QQQ, $MSFT, $GOOGL, $AMZN. "
            * 100
        )

        # Test sentiment analysis with large text
        with patch(
            "app.services.sentiment.SentimentIntensityAnalyzer"
        ) as mock_analyzer_class:
            mock_analyzer = Mock()
            mock_analyzer.polarity_scores.return_value = {
                "pos": 0.6,
                "neu": 0.3,
                "neg": 0.1,
                "compound": 0.5,
            }
            mock_analyzer_class.return_value = mock_analyzer

            sentiment_service = SentimentService()

            start_time = time.time()
            result = sentiment_service.analyze_sentiment(large_text)
            end_time = time.time()

            analysis_time = end_time - start_time

            # Verify results
            assert result == 0.5
            assert analysis_time < 1.0  # Should analyze large text in under 1 second

            print(
                f"Analyzed large text ({len(large_text)} chars) in {analysis_time:.2f} seconds"
            )
            print(
                f"Processing rate: {len(large_text)/analysis_time/1000:.2f} Kchars/sec"
            )

    @pytest.mark.skip(
        reason="Batch performance test temporarily disabled - SQLite incompatibility"
    )
    def test_batch_processing_performance(self, db_session, sample_tickers):
        """Test batch processing performance."""
        # Add tickers to database
        for ticker in sample_tickers:
            db_session.add(ticker)
        db_session.commit()

        # Create test articles
        articles = []
        for i in range(200):  # Test with 200 articles
            article = Article(
                source="reddit",
                url=f"https://reddit.com/test_{i}",
                published_at=datetime.now(UTC),
                title=f"Test Post {i} about $AAPL",
                text=f"Test content {i} with ticker mentions.",
                lang="en",
                reddit_id=f"test_{i}",
                subreddit="test",
                author=f"user_{i}",
                upvotes=i * 10,
                num_comments=i * 5,
                reddit_url=f"https://reddit.com/test_{i}",
            )
            articles.append(article)

        # Test batch processing
        with (
            patch("ingest.linker.get_content_scraper"),
            patch("ingest.linker.get_context_analyzer") as mock_context,
        ):

            mock_context.return_value.analyze_ticker_relevance.return_value = (
                0.8,
                ["Strong context"],
            )

            linker = TickerLinker(sample_tickers)

            start_time = time.time()

            # Process in batches
            batch_size = 50
            total_links = 0

            for i in range(0, len(articles), batch_size):
                batch = articles[i : i + batch_size]
                batch_links = linker.link_articles_to_db(batch)
                total_links += sum(len(links) for _, links in batch_links)

            end_time = time.time()
            batch_time = end_time - start_time

            # Verify results
            assert total_links > 0
            assert batch_time < 15.0  # Should process 200 articles in under 15 seconds

            print(
                f"Processed {len(articles)} articles in batches of {batch_size} in {batch_time:.2f} seconds"
            )
            print(f"Average time per article: {batch_time/len(articles)*1000:.2f} ms")
            print(f"Total ticker links: {total_links}")
