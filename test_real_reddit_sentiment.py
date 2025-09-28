#!/usr/bin/env python3
"""Test sentiment analysis on real Reddit data from the database."""

import logging
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Tuple, Dict, Any
import time

from tqdm import tqdm

from sqlalchemy import select, func
from sqlalchemy.orm import Session

from app.db.models import Article, ArticleTicker, Ticker
from app.db.session import SessionLocal
from app.services.sentiment import get_sentiment_service
from app.services.llm_sentiment import get_llm_sentiment_service

logger = logging.getLogger(__name__)


def setup_logging(verbose: bool = False) -> None:
    """Setup logging configuration."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )


def get_reddit_sample_data(db: Session, limit: int = 20) -> List[Dict[str, Any]]:
    """Get sample Reddit articles from the database.
    
    Args:
        db: Database session
        limit: Maximum number of articles to retrieve
        
    Returns:
        List of article dictionaries with metadata
    """
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
            # For comments, only use the comment text
            content = row.text or ""
        else:
            # For posts, combine title and text
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


def analyze_sentiment_parallel(articles: List[Dict[str, Any]], max_workers: int = 4) -> List[Dict[str, Any]]:
    """Analyze sentiment for multiple articles in parallel.
    
    Args:
        articles: List of article dictionaries
        max_workers: Maximum number of parallel workers
        
    Returns:
        List of results with sentiment scores
    """
    def analyze_single_article(article: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze sentiment for a single article."""
        result = {
            'article': article,
            'vader_score': None,
            'vader_label': "ERROR",
            'llm_score': None,
            'llm_label': "ERROR",
            'existing_score': article['existing_sentiment']
        }
        
        try:
            # VADER analysis
            vader_service = get_sentiment_service()
            vader_score = vader_service.analyze_sentiment(article['content'])
            vader_label = vader_service.get_sentiment_label(vader_score)
            result['vader_score'] = vader_score
            result['vader_label'] = vader_label
        except Exception as e:
            print(f"    VADER error for article {article['id']}: {e}")
        
        try:
            # LLM analysis
            llm_service = get_llm_sentiment_service()
            llm_score = llm_service.analyze_sentiment(article['content'])
            llm_label = llm_service.get_sentiment_label(llm_score)
            result['llm_score'] = llm_score
            result['llm_label'] = llm_label
        except Exception as e:
            print(f"    LLM error for article {article['id']}: {e}")
        
        return result
    
    # Process articles in parallel
    print(f"Processing {len(articles)} articles with {max_workers} parallel workers...")
    start_time = time.time()
    
    results = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all tasks
        future_to_article = {
            executor.submit(analyze_single_article, article): article 
            for article in articles
        }
        
        # Collect results as they complete with progress bar
        with tqdm(total=len(articles), desc="Analyzing sentiment", unit="articles") as pbar:
            for future in as_completed(future_to_article):
                result = future.result()
                results.append(result)
                
                # Update progress bar with article info
                article = result['article']
                pbar.set_postfix({
                    'Current': f"r/{article['subreddit']}" if article['subreddit'] else "Unknown",
                    'VADER': f"{result['vader_label']}" if result['vader_score'] is not None else "ERROR",
                    'LLM': f"{result['llm_label']}" if result['llm_score'] is not None else "ERROR"
                })
                pbar.update(1)
    
    end_time = time.time()
    print(f"✅ Parallel processing completed in {end_time - start_time:.1f} seconds")
    
    # Sort results by original order (article id)
    results.sort(key=lambda x: x['article']['id'])
    return results


def compare_sentiment_on_reddit_data(sample_size: int = 20, max_workers: int = 4) -> None:
    """Compare VADER vs LLM sentiment analysis on real Reddit data."""
    setup_logging(True)
    
    print("=" * 100)
    print("REAL REDDIT DATA SENTIMENT ANALYSIS COMPARISON")
    print("=" * 100)
    
    # Get database session
    db = SessionLocal()
    try:
        # Get Reddit sample data
        print(f"Fetching {sample_size} Reddit articles from database...")
        with tqdm(desc="Querying database", unit="query") as pbar:
            reddit_articles = get_reddit_sample_data(db, sample_size)
            pbar.update(1)
        
        if not reddit_articles:
            print("❌ No Reddit articles found in database")
            return
        
        print(f"✅ Found {len(reddit_articles)} Reddit articles")
        
        # Initialize services
        try:
            vader_service = get_sentiment_service()
            print("✅ VADER service initialized")
        except Exception as e:
            print(f"❌ VADER service failed: {e}")
            return
        
        try:
            llm_service = get_llm_sentiment_service()
            print("✅ LLM service initialized")
            print(f"   Model: {llm_service.model_name}")
        except Exception as e:
            print(f"❌ LLM service failed: {e}")
            return
        
        print("\n" + "=" * 100)
        print("SENTIMENT ANALYSIS RESULTS")
        print("=" * 100)
        
        # Process articles in parallel
        results = analyze_sentiment_parallel(reddit_articles, max_workers=max_workers)
        
        # Display results
        for i, result in enumerate(results, 1):
            article = result['article']
            print(f"\n{i:2d}. r/{article['subreddit']} | {article['upvotes']} upvotes | Tickers: {article['tickers']}")
            print(f"    Title: {article['title'][:80]}{'...' if len(article['title']) > 80 else ''}")
            if article['text'] and article['text'].strip():
                print(f"    Text:  {article['text'][:80]}{'...' if len(article['text']) > 80 else ''}")
            
            # Current sentiment (if any)
            if article['existing_sentiment'] is not None:
                existing_label = get_sentiment_label(article['existing_sentiment'])
                print(f"    Current: {existing_label:8} ({article['existing_sentiment']:6.3f})")
            else:
                print(f"    Current: No sentiment data")
            
            # Display results
            print(f"    VADER:   {result['vader_label']:8} ({result['vader_score']:6.3f})" if result['vader_score'] is not None else f"    VADER:   ERROR")
            print(f"    LLM:     {result['llm_label']:8} ({result['llm_score']:6.3f})" if result['llm_score'] is not None else f"    LLM:     ERROR")
        
        # Analysis summary
        print("\n" + "=" * 100)
        print("ANALYSIS SUMMARY")
        print("=" * 100)
        
        print("Calculating summary statistics...")
        with tqdm(desc="Computing stats", total=3, unit="step") as pbar:
            vader_scores = [r['vader_score'] for r in results if r['vader_score'] is not None]
            pbar.update(1)
            
            llm_scores = [r['llm_score'] for r in results if r['llm_score'] is not None]
            pbar.update(1)
            
            # Calculate agreement
            agreement = sum(1 for r in results 
                          if (r['vader_score'] is not None and r['llm_score'] is not None and 
                              r['vader_label'] == r['llm_label']))
            pbar.update(1)
        
        if vader_scores and llm_scores:
            vader_avg = sum(vader_scores) / len(vader_scores)
            llm_avg = sum(llm_scores) / len(llm_scores)
            
            print(f"Average sentiment scores:")
            print(f"  VADER: {vader_avg:6.3f}")
            print(f"  LLM:   {llm_avg:6.3f}")
            
            # Distribution analysis
            vader_pos = len([s for s in vader_scores if s > 0.1])
            vader_neu = len([s for s in vader_scores if -0.1 <= s <= 0.1])
            vader_neg = len([s for s in vader_scores if s < -0.1])
            
            llm_pos = len([s for s in llm_scores if s > 0.1])
            llm_neu = len([s for s in llm_scores if -0.1 <= s <= 0.1])
            llm_neg = len([s for s in llm_scores if s < -0.1])
            
            print(f"\nSentiment distribution:")
            print(f"  VADER: {vader_pos} Positive, {vader_neu} Neutral, {vader_neg} Negative")
            print(f"  LLM:   {llm_pos} Positive, {llm_neu} Neutral, {llm_neg} Negative")
            
            agreement_pct = (agreement / len(results)) * 100
            print(f"\nAgreement: {agreement}/{len(results)} ({agreement_pct:.1f}%)")
            
            # High confidence examples
            print(f"\nHighest confidence positive examples (LLM):")
            positive_examples = [(r['article']['title'], r['llm_score']) 
                               for r in results if r['llm_score'] and r['llm_score'] > 0.5]
            positive_examples.sort(key=lambda x: x[1], reverse=True)
            for title, score in positive_examples[:3]:
                print(f"  {score:6.3f}: {title[:60]}{'...' if len(title) > 60 else ''}")
            
            print(f"\nHighest confidence negative examples (LLM):")
            negative_examples = [(r['article']['title'], r['llm_score']) 
                               for r in results if r['llm_score'] and r['llm_score'] < -0.5]
            negative_examples.sort(key=lambda x: x[1])
            for title, score in negative_examples[:3]:
                print(f"  {score:6.3f}: {title[:60]}{'...' if len(title) > 60 else ''}")
    
    except Exception as e:
        logger.error(f"Error during sentiment comparison: {e}")
    finally:
        db.close()


def get_sentiment_label(score: float) -> str:
    """Get sentiment label from score."""
    if score >= 0.1:
        return "Positive"
    elif score <= -0.1:
        return "Negative"
    else:
        return "Neutral"


def analyze_by_subreddit(sample_size: int = 50) -> None:
    """Analyze sentiment patterns by subreddit."""
    print("\n" + "=" * 100)
    print("SENTIMENT ANALYSIS BY SUBREDDIT")
    print("=" * 100)
    
    db = SessionLocal()
    try:
        # Get articles grouped by subreddit
        query = (
            db.query(
                Article.subreddit,
                func.count(Article.id).label('count'),
                func.avg(Article.sentiment).label('avg_sentiment')
            )
            .filter(Article.source.like('%reddit%'))
            .filter(Article.sentiment.isnot(None))
            .filter(Article.subreddit.isnot(None))
            .group_by(Article.subreddit)
            .having(func.count(Article.id) >= 5)  # At least 5 articles
            .order_by(func.count(Article.id).desc())
        )
        
        subreddit_stats = query.all()
        
        if subreddit_stats:
            print(f"Subreddit sentiment analysis (minimum 5 articles):")
            print(f"{'Subreddit':<20} {'Articles':<10} {'Avg Sentiment':<15} {'Label':<10}")
            print("-" * 60)
            
            for subreddit, count, avg_sentiment in subreddit_stats:
                if avg_sentiment is not None:
                    label = get_sentiment_label(avg_sentiment)
                    print(f"r/{subreddit:<19} {count:<10} {avg_sentiment:<15.3f} {label:<10}")
                else:
                    print(f"r/{subreddit:<19} {count:<10} {'N/A':<15} {'N/A':<10}")
        else:
            print("No subreddit data found with sufficient articles")
    
    except Exception as e:
        logger.error(f"Error during subreddit analysis: {e}")
    finally:
        db.close()


def main() -> None:
    """Main function."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Test sentiment analysis on real Reddit data")
    parser.add_argument(
        "--sample-size",
        type=int,
        default=20,
        help="Number of Reddit articles to analyze (default: 20)",
    )
    parser.add_argument(
        "--max-workers",
        type=int,
        default=4,
        help="Maximum number of parallel workers (default: 4)",
    )
    parser.add_argument(
        "--skip-subreddit-analysis",
        action="store_true",
        help="Skip subreddit analysis",
    )
    
    args = parser.parse_args()
    
    try:
        compare_sentiment_on_reddit_data(
            sample_size=args.sample_size, 
            max_workers=args.max_workers
        )
        
        if not args.skip_subreddit_analysis:
            analyze_by_subreddit()
    except KeyboardInterrupt:
        print("\nTest interrupted by user")
    except Exception as e:
        print(f"Test failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
