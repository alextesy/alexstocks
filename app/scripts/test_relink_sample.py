"""Test re-linking on a sample of articles to verify the expanded ticker coverage."""

import logging
from typing import Any

from app.db.models import Article, ArticleTicker, Ticker
from app.scripts.relink_all_articles import ArticleRelinkingService

logger = logging.getLogger(__name__)


def test_relink_sample(sample_size: int = 20):
    """Test re-linking on a sample of articles."""
    print(f"\n{'='*60}")
    print("TESTING EXPANDED TICKER LINKING")
    print(f"{'='*60}")

    service: Any = ArticleRelinkingService()

    try:
        # Get sample of recent articles
        recent_articles = (
            service.db.query(Article)
            .order_by(Article.published_at.desc())
            .limit(sample_size)
            .all()
        )

        if not recent_articles:
            print("❌ No articles found for testing")
            return

        print(f"📊 Testing on {len(recent_articles)} recent articles")

        # Initialize ticker linker
        if not service.initialize_linker():
            print("❌ Failed to initialize ticker linker")
            return

        # Show before/after for each article
        total_old_links = 0
        total_new_links = 0
        articles_with_improvements = 0

        for i, article in enumerate(recent_articles, 1):
            # Get existing links
            existing_links = (
                service.db.query(ArticleTicker)
                .filter(ArticleTicker.article_id == article.id)
                .all()
            )

            old_tickers = [link.ticker for link in existing_links]
            old_count = len(old_tickers)

            # Test new linking (without clearing existing)
            ticker_links = service.ticker_linker.link_article(
                article, use_title_only=True
            )
            new_tickers = [link.ticker for link in ticker_links]
            new_count = len(new_tickers)

            # Calculate improvements
            additional_tickers = set(new_tickers) - set(old_tickers)

            print(f"\n📰 Article {i}: {article.title[:60]}...")
            print(f"   Published: {article.published_at.strftime('%Y-%m-%d %H:%M')}")
            print(f"   Source: {article.source}")
            print(f"   Old links: {old_count} tickers {old_tickers}")
            print(f"   New links: {new_count} tickers {new_tickers}")

            if additional_tickers:
                print(f"   ✅ Additional: {list(additional_tickers)}")
                articles_with_improvements += 1
            elif new_count > old_count:
                print("   ✅ More tickers found")
                articles_with_improvements += 1
            elif new_count == old_count and set(new_tickers) != set(old_tickers):
                print("   🔄 Different tickers found")
                articles_with_improvements += 1
            else:
                print("   ➡️  No change")

            total_old_links += old_count
            total_new_links += new_count

        # Summary
        print(f"\n{'='*60}")
        print("SAMPLE TEST RESULTS")
        print(f"{'='*60}")
        print(f"Articles tested: {len(recent_articles)}")
        print(f"Articles with improvements: {articles_with_improvements}")
        print(
            f"Improvement rate: {(articles_with_improvements/len(recent_articles)*100):.1f}%"
        )
        print(f"Total old links: {total_old_links}")
        print(f"Total new links: {total_new_links}")
        print(
            f"Link increase: {((total_new_links/max(total_old_links,1)-1)*100):+.1f}%"
        )

        # Show ticker database stats
        total_tickers = service.db.query(Ticker).count()
        sp500_tickers = service.db.query(Ticker).filter(Ticker.is_sp500).count()

        print("\nTicker Database:")
        print(f"  Total tickers: {total_tickers:,}")
        print(f"  S&P 500 tickers: {sp500_tickers}")
        print(f"  Other tickers: {total_tickers - sp500_tickers:,}")

        if articles_with_improvements > 0:
            print("\n✅ Expanded ticker database shows promise!")
            print("   Recommend running full re-linking on all articles.")
        else:
            print("\n🤔 No improvements detected in sample.")
            print("   May want to investigate ticker linking logic.")

    finally:
        service.close()


def main():
    """Main function."""
    logging.basicConfig(level=logging.INFO)
    test_relink_sample(sample_size=20)


if __name__ == "__main__":
    main()
