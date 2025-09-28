#!/usr/bin/env python3
"""Test script for improved ticker linking system."""

import logging
from datetime import UTC, datetime

from app.db.models import Article, Ticker
from app.db.session import SessionLocal
from ingest.linker import TickerLinker

logger = logging.getLogger(__name__)


def create_test_articles() -> list[Article]:
    """Create test articles with various ticker mentions."""
    test_articles = [
        # Article about Visa Inc (should match)
        Article(
            source="test",
            url="https://example.com/visa-earnings",
            published_at=datetime.now(UTC),
            title="Visa Inc Reports Strong Q4 Earnings, Stock Rises",
            text="Visa Inc (V) reported strong quarterly earnings today. The payment processing company saw revenue growth of 15% year-over-year. Visa's CEO announced new partnerships with fintech companies. The stock price rose 5% in after-hours trading.",
        ),
        
        # Article about visa applications (should NOT match)
        Article(
            source="test",
            url="https://example.com/visa-application",
            published_at=datetime.now(UTC),
            title="New Visa Requirements for International Students",
            text="The US government has announced new visa requirements for international students. The visa application process will now require additional documentation. Students must submit their visa applications by the end of the month. The visa office will process applications within 30 days.",
        ),
        
        # Article about Apple (should match)
        Article(
            source="test",
            url="https://example.com/apple-iphone",
            published_at=datetime.now(UTC),
            title="Apple Unveils New iPhone with Advanced AI Features",
            text="Apple Inc (AAPL) unveiled its latest iPhone model today. The new device features advanced AI capabilities and improved camera technology. Apple's stock price increased following the announcement. The company expects strong sales in the holiday season.",
        ),
        
        # Article about Tesla (should match)
        Article(
            source="test",
            url="https://example.com/tesla-autopilot",
            published_at=datetime.now(UTC),
            title="Tesla's Autopilot Technology Gets Regulatory Approval",
            text="Tesla Inc (TSLA) received regulatory approval for its latest autopilot technology. The electric vehicle manufacturer's stock rose 8% on the news. Tesla's CEO announced plans to expand production capacity. The company expects to deliver 500,000 vehicles this quarter.",
        ),
        
        # Article with multiple tickers (should match both)
        Article(
            source="test",
            url="https://example.com/tech-stocks",
            published_at=datetime.now(UTC),
            title="Tech Stocks Rally as Microsoft and Google Report Strong Earnings",
            text="Microsoft Corporation (MSFT) and Alphabet Inc (GOOGL) both reported strong quarterly earnings. Microsoft's cloud services division saw 25% growth. Google's advertising revenue increased by 18%. Both stocks rose in after-hours trading. Analysts expect continued growth in the tech sector.",
        ),
        
        # Article with ambiguous ticker mention (should have low confidence)
        Article(
            source="test",
            url="https://example.com/ambiguous",
            published_at=datetime.now(UTC),
            title="The Letter V Appears in Many Company Names",
            text="The letter V is commonly used in company names and ticker symbols. Many companies choose V as their ticker symbol. This creates confusion for investors. The letter V can represent different companies in different contexts.",
        ),
    ]
    
    return test_articles


def test_improved_linking():
    """Test the improved ticker linking system."""
    logging.basicConfig(level=logging.INFO)
    
    # Get database session
    session = SessionLocal()
    
    try:
        # Get tickers from database
        tickers = session.query(Ticker).all()
        if not tickers:
            logger.error("No tickers found in database. Please seed tickers first.")
            return
        
        # Create linker
        linker = TickerLinker(tickers)
        
        # Create test articles
        test_articles = create_test_articles()
        
        # Test linking
        results = linker.link_articles(test_articles)
        
        # Display results
        print("\n" + "="*80)
        print("IMPROVED TICKER LINKING TEST RESULTS")
        print("="*80)
        
        for article, ticker_links in results:
            print(f"\nArticle: {article.title}")
            print(f"URL: {article.url}")
            print(f"Text: {article.text[:100]}...")
            print(f"Linked to {len(ticker_links)} tickers:")
            
            for link in ticker_links:
                print(f"  - {link.ticker}: {link.confidence:.2f} confidence")
                print(f"    Matched terms: {', '.join(link.matched_terms)}")
                print(f"    Reasoning: {', '.join(link.reasoning)}")
            
            if not ticker_links:
                print("  - No tickers linked (below confidence threshold)")
        
        # Summary
        total_links = sum(len(links) for _, links in results)
        linked_articles = sum(1 for _, links in results if links)
        
        print(f"\n" + "="*80)
        print("SUMMARY")
        print("="*80)
        print(f"Total articles: {len(test_articles)}")
        print(f"Articles with links: {linked_articles}")
        print(f"Total ticker links: {total_links}")
        print(f"Average links per article: {total_links/len(test_articles):.2f}")
        
        # Test specific cases
        print(f"\n" + "="*80)
        print("SPECIFIC TEST CASES")
        print("="*80)
        
        # Test Visa Inc article
        visa_article = test_articles[0]
        visa_links = linker.link_article(visa_article)
        visa_link = next((link for link in visa_links if link.ticker == "V"), None)
        if visa_link:
            print(f"✓ Visa Inc article correctly linked to V with {visa_link.confidence:.2f} confidence")
        else:
            print("✗ Visa Inc article NOT linked to V")
        
        # Test visa application article
        visa_app_article = test_articles[1]
        visa_app_links = linker.link_article(visa_app_article)
        visa_app_link = next((link for link in visa_app_links if link.ticker == "V"), None)
        if visa_app_link:
            print(f"✗ Visa application article incorrectly linked to V with {visa_app_link.confidence:.2f} confidence")
        else:
            print("✓ Visa application article correctly NOT linked to V")
        
        # Test Apple article
        apple_article = test_articles[2]
        apple_links = linker.link_article(apple_article)
        apple_link = next((link for link in apple_links if link.ticker == "AAPL"), None)
        if apple_link:
            print(f"✓ Apple article correctly linked to AAPL with {apple_link.confidence:.2f} confidence")
        else:
            print("✗ Apple article NOT linked to AAPL")
        
        # Test ambiguous article
        ambiguous_article = test_articles[5]
        ambiguous_links = linker.link_article(ambiguous_article)
        ambiguous_link = next((link for link in ambiguous_links if link.ticker == "V"), None)
        if ambiguous_link:
            print(f"✗ Ambiguous article incorrectly linked to V with {ambiguous_link.confidence:.2f} confidence")
        else:
            print("✓ Ambiguous article correctly NOT linked to V")
        
    finally:
        session.close()


if __name__ == "__main__":
    test_improved_linking()
