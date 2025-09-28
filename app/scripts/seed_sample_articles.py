"""Seed sample articles with ticker links for demonstration."""

import logging
from datetime import UTC, datetime, timedelta

from app.db.models import Article, ArticleTicker
from app.db.session import SessionLocal

logger = logging.getLogger(__name__)


def create_sample_articles() -> list[Article]:
    """Create sample articles with ticker mentions."""
    now = datetime.now(UTC)
    
    articles = [
        Article(
            source="sample",
            url="https://example.com/apple-earnings-beat-expectations",
            published_at=now - timedelta(hours=2),
            title="Apple Inc (AAPL) Earnings Beat Expectations with Strong iPhone Sales",
            text="Apple Inc reported better than expected earnings for Q4, driven by strong iPhone sales and services revenue. The company's stock $AAPL rose 3% in after-hours trading.",
            lang="en",
        ),
        Article(
            source="sample",
            url="https://example.com/microsoft-ai-investments",
            published_at=now - timedelta(hours=4),
            title="Microsoft Corporation (MSFT) Announces Major AI Investment",
            text="Microsoft Corporation announced a $10 billion investment in artificial intelligence infrastructure. The move positions MSFT as a leader in the AI space.",
            lang="en",
        ),
        Article(
            source="sample",
            url="https://example.com/tesla-stock-surge",
            published_at=now - timedelta(hours=6),
            title="Tesla Inc (TSLA) Stock Surges on Delivery Numbers",
            text="Tesla Inc reported record delivery numbers for the quarter, sending TSLA stock up 8% in pre-market trading. The electric vehicle maker continues to dominate the market.",
            lang="en",
        ),
        Article(
            source="sample",
            url="https://example.com/google-alphabet-earnings",
            published_at=now - timedelta(hours=8),
            title="Alphabet Inc (GOOGL) Reports Strong Q4 Results",
            text="Alphabet Inc, the parent company of Google, reported strong quarterly results with advertising revenue up 12%. GOOGL shares gained 4% following the announcement.",
            lang="en",
        ),
        Article(
            source="sample",
            url="https://example.com/amazon-aws-growth",
            published_at=now - timedelta(hours=10),
            title="Amazon.com Inc (AMZN) AWS Division Shows Strong Growth",
            text="Amazon.com Inc's cloud computing division AWS reported 20% revenue growth, driving AMZN stock higher. The company continues to lead in cloud infrastructure.",
            lang="en",
        ),
        Article(
            source="sample",
            url="https://example.com/nvidia-ai-chip-demand",
            published_at=now - timedelta(hours=12),
            title="NVIDIA Corporation (NVDA) Sees Surging Demand for AI Chips",
            text="NVIDIA Corporation reported unprecedented demand for its AI chips, with NVDA stock reaching new all-time highs. The company is at the center of the AI revolution.",
            lang="en",
        ),
        Article(
            source="sample",
            url="https://example.com/meta-platforms-metaverse",
            published_at=now - timedelta(hours=14),
            title="Meta Platforms Inc (META) Doubles Down on Metaverse",
            text="Meta Platforms Inc announced new investments in metaverse technology, with META stock responding positively to the news. The company remains committed to VR/AR development.",
            lang="en",
        ),
        Article(
            source="sample",
            url="https://example.com/berkshire-hathaway-investment",
            published_at=now - timedelta(hours=16),
            title="Berkshire Hathaway Inc (BRK.B) Makes New Investment",
            text="Berkshire Hathaway Inc, led by Warren Buffett, announced a new major investment. BRK.B shares were stable following the news as investors await more details.",
            lang="en",
        ),
    ]
    
    return articles


def create_article_ticker_links(articles: list[Article]) -> list[ArticleTicker]:
    """Create article-ticker relationships based on content."""
    links = []
    
    # Map articles to their primary tickers
    article_ticker_map = {
        "apple-earnings-beat-expectations": [("AAPL", 0.9)],
        "microsoft-ai-investments": [("MSFT", 0.9)],
        "tesla-stock-surge": [("TSLA", 0.9)],
        "google-alphabet-earnings": [("GOOGL", 0.9)],
        "amazon-aws-growth": [("AMZN", 0.9)],
        "nvidia-ai-chip-demand": [("NVDA", 0.9)],
        "meta-platforms-metaverse": [("META", 0.9)],
        "berkshire-hathaway-investment": [("BRK.B", 0.9)],
    }
    
    for article in articles:
        # Extract article key from URL
        article_key = article.url.split("/")[-1]
        
        if article_key in article_ticker_map:
            for ticker_symbol, confidence in article_ticker_map[article_key]:
                link = ArticleTicker(
                    article_id=article.id,  # Will be set after article is saved
                    ticker=ticker_symbol,
                    confidence=confidence
                )
                links.append((article, link))
    
    return links


def seed_sample_articles() -> bool:
    """Seed the database with sample articles and ticker links."""
    db = SessionLocal()
    try:
        # Clear existing sample articles
        db.query(ArticleTicker).delete()
        db.query(Article).filter(Article.source == "sample").delete()
        db.commit()
        logger.info("Cleared existing sample articles")
        
        # Create sample articles
        articles = create_sample_articles()
        
        # Save articles and get their IDs
        saved_articles = []
        for article in articles:
            db.add(article)
            db.flush()  # Get the ID
            saved_articles.append(article)
        
        # Create article-ticker links
        article_links = create_article_ticker_links(saved_articles)
        
        # Save the links
        for article, link in article_links:
            link.article_id = article.id
            db.add(link)
        
        db.commit()
        
        logger.info(f"Successfully seeded {len(saved_articles)} sample articles with {len(article_links)} ticker links")
        
        # Verify insertion
        article_count = db.query(Article).filter(Article.source == "sample").count()
        link_count = db.query(ArticleTicker).join(Article).filter(Article.source == "sample").count()
        logger.info(f"Sample articles in database: {article_count}")
        logger.info(f"Sample article-ticker links: {link_count}")
        
        return True
        
    except Exception as e:
        logger.error(f"Failed to seed sample articles: {e}")
        db.rollback()
        return False
    finally:
        db.close()


def main() -> None:
    """Main function for seeding sample articles."""
    logging.basicConfig(level=logging.INFO)
    logger.info("Starting sample article seeding...")
    
    success = seed_sample_articles()
    
    if success:
        logger.info("Sample article seeding completed successfully")
    else:
        logger.error("Sample article seeding failed")


if __name__ == "__main__":
    main()
