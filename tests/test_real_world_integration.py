"""Real-world integration tests using actual database data."""

import pytest
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Any
import time

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db.models import Article, ArticleTicker, Ticker
from app.db.session import SessionLocal
from app.services.sentiment import get_sentiment_service
from app.services.llm_sentiment import get_llm_sentiment_service

logger = logging.getLogger(__name__)


@pytest.mark.integration
@pytest.mark.slow
class TestRealWorldIntegration:
    """Test integration with real database data."""

    @pytest.fixture(autouse=True)
    def setup_real_db(self):
        """Setup real database session for integration tests."""
        self.db = SessionLocal()
        yield
        self.db.close()

    def get_reddit_sample_data(self, db: Session, limit: int = 20) -> List[Dict[str, Any]]:
        """Get sample Reddit articles from the database."""
        # Get Reddit articles with ticker information
        query = (
            db.query(
                Article.id,
                Article.title,
                Article.text,
                Article.source,
                Article.subreddit,
                Article.upvotes,
                Article.sentiment,
                func.string_agg(ArticleTicker.ticker, ', ').label('tickers')
            )
            .outerjoin(ArticleTicker, Article.id == ArticleTicker.article_id)
            .filter(Article.source.like('%reddit%'))
            .filter(Article.title.isnot(None))
            .filter(Article.title != '')
            .group_by(Article.id, Article.title, Article.text, Article.source, 
                     Article.subreddit, Article.upvotes, Article.sentiment)
            .order_by(Article.upvotes.desc().nullslast())
            .limit(limit)
        )
        
        results = []
        for row in query.all():
            # For Reddit comments, use only the text. For posts, use title + text
            if row.source == 'reddit_comment':
                content = row.text or ""
            else:
                content = row.title
                if row.text and row.text.strip():
                    content += " " + row.text
            
            results.append({
                'id': row.id,
                'title': row.title,
                'text': row.text,
                'content': content,
                'source': row.source,
                'subreddit': row.subreddit,
                'upvotes': row.upvotes or 0,
                'existing_sentiment': row.sentiment,
                'tickers': row.tickers or 'None'
            })
        
        return results

    def test_sentiment_analysis_on_real_reddit_data(self):
        """Test sentiment analysis on real Reddit data from database."""
        # Get sample Reddit data
        reddit_articles = self.get_reddit_sample_data(self.db, limit=10)
        
        if not reddit_articles:
            pytest.skip("No Reddit articles found in database")
        
        # Initialize services
        vader_service = get_sentiment_service()
        
        # Test VADER sentiment analysis
        results = []
        for article in reddit_articles:
            try:
                vader_score = vader_service.analyze_sentiment(article['content'])
                vader_label = vader_service.get_sentiment_label(vader_score)
                
                results.append({
                    'article_id': article['id'],
                    'title': article['title'],
                    'vader_score': vader_score,
                    'vader_label': vader_label,
                    'existing_sentiment': article['existing_sentiment']
                })
            except Exception as e:
                logger.warning(f"VADER analysis failed for article {article['id']}: {e}")
        
        # Verify we got results
        assert len(results) > 0, "No sentiment analysis results"
        
        # Verify sentiment scores are in valid range
        for result in results:
            assert -1.0 <= result['vader_score'] <= 1.0, f"Invalid sentiment score: {result['vader_score']}"
            assert result['vader_label'] in ['Positive', 'Negative', 'Neutral'], f"Invalid sentiment label: {result['vader_label']}"

    def test_llm_sentiment_analysis_on_real_data(self):
        """Test LLM sentiment analysis on real Reddit data."""
        # Get sample Reddit data
        reddit_articles = self.get_reddit_sample_data(self.db, limit=5)
        
        if not reddit_articles:
            pytest.skip("No Reddit articles found in database")
        
        try:
            llm_service = get_llm_sentiment_service()
        except Exception as e:
            pytest.skip(f"LLM service not available: {e}")
        
        # Test LLM sentiment analysis
        results = []
        for article in reddit_articles:
            try:
                llm_score = llm_service.analyze_sentiment(article['content'])
                llm_label = llm_service.get_sentiment_label(llm_score)
                
                results.append({
                    'article_id': article['id'],
                    'title': article['title'],
                    'llm_score': llm_score,
                    'llm_label': llm_label
                })
            except Exception as e:
                logger.warning(f"LLM analysis failed for article {article['id']}: {e}")
        
        # Verify we got results
        assert len(results) > 0, "No LLM sentiment analysis results"
        
        # Verify sentiment scores are in valid range
        for result in results:
            assert -1.0 <= result['llm_score'] <= 1.0, f"Invalid LLM sentiment score: {result['llm_score']}"
            assert result['llm_label'] in ['Positive', 'Negative', 'Neutral'], f"Invalid LLM sentiment label: {result['llm_label']}"

    def test_sentiment_analysis_performance_on_real_data(self):
        """Test performance of sentiment analysis on real data."""
        # Get sample Reddit data
        reddit_articles = self.get_reddit_sample_data(self.db, limit=20)
        
        if not reddit_articles:
            pytest.skip("No Reddit articles found in database")
        
        vader_service = get_sentiment_service()
        
        # Test VADER performance
        start_time = time.time()
        for article in reddit_articles:
            try:
                vader_service.analyze_sentiment(article['content'])
            except Exception:
                pass  # Skip failed analyses
        vader_time = time.time() - start_time
        
        # Performance should be reasonable (less than 1 second for 20 articles)
        assert vader_time < 1.0, f"VADER performance too slow: {vader_time:.2f}s for {len(reddit_articles)} articles"
        
        # Average time per article should be reasonable
        avg_time_per_article = vader_time / len(reddit_articles)
        assert avg_time_per_article < 0.1, f"VADER too slow per article: {avg_time_per_article:.3f}s"

    def test_parallel_sentiment_analysis(self):
        """Test parallel sentiment analysis on real data."""
        # Get sample Reddit data
        reddit_articles = self.get_reddit_sample_data(self.db, limit=10)
        
        if not reddit_articles:
            pytest.skip("No Reddit articles found in database")
        
        vader_service = get_sentiment_service()
        
        def analyze_article(article: Dict[str, Any]) -> Dict[str, Any]:
            """Analyze sentiment for a single article."""
            try:
                score = vader_service.analyze_sentiment(article['content'])
                label = vader_service.get_sentiment_label(score)
                return {
                    'article_id': article['id'],
                    'score': score,
                    'label': label,
                    'success': True
                }
            except Exception as e:
                return {
                    'article_id': article['id'],
                    'error': str(e),
                    'success': False
                }
        
        # Process articles in parallel
        start_time = time.time()
        results = []
        with ThreadPoolExecutor(max_workers=4) as executor:
            future_to_article = {
                executor.submit(analyze_article, article): article 
                for article in reddit_articles
            }
            
            for future in as_completed(future_to_article):
                result = future.result()
                results.append(result)
        
        parallel_time = time.time() - start_time
        
        # Verify parallel processing worked
        successful_results = [r for r in results if r['success']]
        assert len(successful_results) > 0, "No successful parallel analyses"
        
        # Parallel processing should be faster than sequential (roughly)
        assert parallel_time < 2.0, f"Parallel processing too slow: {parallel_time:.2f}s"

    def test_subreddit_sentiment_analysis(self):
        """Test sentiment analysis patterns by subreddit."""
        # Get articles grouped by subreddit
        query = (
            self.db.query(
                Article.subreddit,
                func.count(Article.id).label('count'),
                func.avg(Article.sentiment).label('avg_sentiment')
            )
            .filter(Article.source.like('%reddit%'))
            .filter(Article.sentiment.isnot(None))
            .filter(Article.subreddit.isnot(None))
            .group_by(Article.subreddit)
            .having(func.count(Article.id) >= 3)  # At least 3 articles
            .order_by(func.count(Article.id).desc())
        )
        
        subreddit_stats = query.all()
        
        if not subreddit_stats:
            pytest.skip("No subreddit data found with sufficient articles")
        
        # Verify we have reasonable subreddit data
        assert len(subreddit_stats) > 0, "No subreddit statistics found"
        
        # Check that sentiment averages are in valid range
        for subreddit, count, avg_sentiment in subreddit_stats:
            if avg_sentiment is not None:
                assert -1.0 <= avg_sentiment <= 1.0, f"Invalid average sentiment for r/{subreddit}: {avg_sentiment}"
                assert count >= 3, f"Insufficient articles for r/{subreddit}: {count}"

    def test_ticker_linking_on_real_reddit_data(self):
        """Test ticker linking on real Reddit data."""
        # Get Reddit articles with text content
        query = (
            self.db.query(Article)
            .filter(Article.source.like('%reddit%'))
            .filter(Article.text.isnot(None))
            .filter(Article.text != '')
            .limit(10)
        )
        
        articles = query.all()
        
        if not articles:
            pytest.skip("No Reddit articles with text content found")
        
        from ingest.linker import TickerLinker
        from app.db.models import Ticker
        # Get tickers from database
        tickers = self.db.query(Ticker).all()
        linker = TickerLinker(tickers)
        
        # Test ticker linking on real articles
        linked_count = 0
        for article in articles:
            try:
                # Extract text for matching
                text = linker._extract_text_for_matching(article)
                
                # Find ticker matches
                matches = linker._find_ticker_matches(text)
                
                if matches:
                    linked_count += 1
                    
                    # Verify matches are valid
                    for ticker, terms in matches.items():
                        assert len(terms) > 0, f"No matched terms for ticker: {ticker}"
                        
            except Exception as e:
                logger.warning(f"Ticker linking failed for article {article.id}: {e}")
        
        # We should find some ticker matches in real Reddit data
        # (This might be 0 if the sample data doesn't contain ticker mentions)
        logger.info(f"Found ticker matches in {linked_count}/{len(articles)} articles")

    def test_end_to_end_pipeline_on_real_data(self):
        """Test complete pipeline on real Reddit data."""
        # Get a Reddit article
        article = (
            self.db.query(Article)
            .filter(Article.source.like('%reddit%'))
            .filter(Article.text.isnot(None))
            .filter(Article.text != '')
            .first()
        )
        
        if not article:
            pytest.skip("No Reddit articles with text content found")
        
        # Test complete pipeline
        from ingest.linker import TickerLinker
        from app.services.sentiment import get_sentiment_service
        from app.db.models import Ticker
        
        # Get tickers from database
        tickers = self.db.query(Ticker).all()
        linker = TickerLinker(tickers)
        sentiment_service = get_sentiment_service()
        
        # 1. Ticker linking
        ticker_links = linker.link_article(article)
        
        # 2. Sentiment analysis
        sentiment_score = sentiment_service.analyze_sentiment(article.text or article.title or "")
        sentiment_label = sentiment_service.get_sentiment_label(sentiment_score)
        
        # 3. Verify results
        assert isinstance(sentiment_score, float), "Sentiment score should be float"
        assert -1.0 <= sentiment_score <= 1.0, f"Invalid sentiment score: {sentiment_score}"
        assert sentiment_label in ['Positive', 'Negative', 'Neutral'], f"Invalid sentiment label: {sentiment_label}"
        
        # Ticker links might be empty if no tickers found in text
        for link in ticker_links:
            assert hasattr(link, 'ticker'), "TickerLink should have ticker attribute"
            assert hasattr(link, 'confidence'), "TickerLink should have confidence attribute"
            assert 0.0 <= link.confidence <= 1.0, f"Invalid confidence: {link.confidence}"
        
        logger.info(f"Pipeline completed: {len(ticker_links)} ticker links, sentiment: {sentiment_label} ({sentiment_score:.3f})")
