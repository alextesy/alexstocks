"""Re-link all existing articles to tickers using the expanded ticker database."""

import logging
import time

from sqlalchemy import func, text

from app.db.models import Article, ArticleTicker, Ticker
from app.db.session import SessionLocal
from ingest.linker import TickerLinker

logger = logging.getLogger(__name__)


class ArticleRelinkingService:
    """Service to re-link all articles with expanded ticker database."""

    def __init__(self):
        self.db = SessionLocal()
        self.ticker_linker = None
        self.stats = {
            "articles_processed": 0,
            "articles_with_new_links": 0,
            "total_new_links": 0,
            "total_removed_links": 0,
            "processing_time": 0.0,
        }

    def initialize_linker(self) -> bool:
        """Initialize the ticker linker with expanded ticker database."""
        logger.info("Loading expanded ticker database...")

        try:
            # Load all tickers from database
            tickers = self.db.query(Ticker).all()

            if not tickers:
                logger.error("No tickers found in database!")
                return False

            logger.info(f"Loaded {len(tickers)} tickers from database")

            # Initialize ticker linker
            self.ticker_linker = TickerLinker(tickers, max_scraping_workers=5)
            logger.info("Ticker linker initialized successfully")

            return True

        except Exception as e:
            logger.error(f"Failed to initialize ticker linker: {e}")
            return False

    def get_articles_to_relink(
        self, batch_size: int = 100, limit: int = None
    ) -> list[Article]:
        """Get articles that need to be re-linked."""
        query = self.db.query(Article).order_by(
            Article.published_at.desc()
        )  # Start with most recent

        if limit:
            query = query.limit(limit)

        return query.all()

    def clear_existing_links(self, article: Article) -> int:
        """Clear existing article-ticker links for an article."""
        existing_links = (
            self.db.query(ArticleTicker)
            .filter(ArticleTicker.article_id == article.id)
            .all()
        )

        count = len(existing_links)

        for link in existing_links:
            self.db.delete(link)

        return count

    def relink_article(self, article: Article, clear_existing: bool = True) -> dict:
        """Re-link a single article to tickers."""
        result = {
            "article_id": article.id,
            "old_links_count": 0,
            "new_links_count": 0,
            "new_tickers": [],
        }

        try:
            # Clear existing links if requested
            if clear_existing:
                result["old_links_count"] = self.clear_existing_links(article)

            # Find new ticker links
            ticker_links = self.ticker_linker.link_article(article, use_title_only=True)

            # Create new ArticleTicker relationships
            for ticker_link in ticker_links:
                article_ticker = ArticleTicker(
                    article_id=article.id,
                    ticker=ticker_link.ticker,
                    confidence=ticker_link.confidence,
                    matched_terms=ticker_link.matched_terms,
                )
                self.db.add(article_ticker)
                result["new_tickers"].append(ticker_link.ticker)

            result["new_links_count"] = len(ticker_links)

            # Commit changes for this article
            self.db.commit()

            return result

        except Exception as e:
            logger.error(f"Failed to relink article {article.id}: {e}")
            self.db.rollback()
            result["error"] = str(e)
            return result

    def relink_all_articles(
        self, batch_size: int = 100, limit: int = None, clear_existing: bool = True
    ) -> dict:
        """Re-link all articles in the database."""
        logger.info("Starting article re-linking process...")
        start_time = time.time()

        if not self.initialize_linker():
            return {"error": "Failed to initialize ticker linker"}

        # Get total article count
        total_articles = self.db.query(Article).count()
        if limit:
            total_articles = min(total_articles, limit)

        logger.info(f"Found {total_articles} articles to process")

        # Process articles in batches
        processed = 0
        batch_start = 0

        while processed < total_articles:
            # Get batch of articles
            batch_articles = (
                self.db.query(Article)
                .order_by(Article.published_at.desc())
                .offset(batch_start)
                .limit(batch_size)
                .all()
            )

            if not batch_articles:
                break

            logger.info(
                f"Processing batch {batch_start + 1}-{batch_start + len(batch_articles)} of {total_articles}"
            )

            # Process each article in the batch
            for article in batch_articles:
                result = self.relink_article(article, clear_existing=clear_existing)

                # Update stats
                self.stats["articles_processed"] += 1

                if result.get("new_links_count", 0) > 0:
                    self.stats["articles_with_new_links"] += 1
                    self.stats["total_new_links"] += result["new_links_count"]

                if result.get("old_links_count", 0) > 0:
                    self.stats["total_removed_links"] += result["old_links_count"]

                # Log progress
                if self.stats["articles_processed"] % 50 == 0:
                    elapsed = time.time() - start_time
                    rate = (
                        self.stats["articles_processed"] / elapsed if elapsed > 0 else 0
                    )
                    logger.info(
                        f"Progress: {self.stats['articles_processed']}/{total_articles} "
                        f"({rate:.1f} articles/sec), "
                        f"New links: {self.stats['total_new_links']}"
                    )

            processed += len(batch_articles)
            batch_start += batch_size

            # Check if we've hit the limit
            if limit and processed >= limit:
                break

        # Final stats
        self.stats["processing_time"] = time.time() - start_time

        logger.info("Article re-linking completed!")
        self.print_summary()

        return self.stats

    def print_summary(self):
        """Print summary of re-linking process."""
        print(f"\n{'='*60}")
        print("ARTICLE RE-LINKING SUMMARY")
        print(f"{'='*60}")
        print(f"Articles Processed: {self.stats['articles_processed']:,}")
        print(f"Articles with New Links: {self.stats['articles_with_new_links']:,}")
        print(f"Total New Links Created: {self.stats['total_new_links']:,}")
        print(f"Total Old Links Removed: {self.stats['total_removed_links']:,}")
        print(f"Processing Time: {self.stats['processing_time']:.1f} seconds")

        if self.stats["articles_processed"] > 0:
            avg_links_per_article = (
                self.stats["total_new_links"] / self.stats["articles_processed"]
            )
            coverage_rate = (
                self.stats["articles_with_new_links"] / self.stats["articles_processed"]
            ) * 100

            print(f"Average Links per Article: {avg_links_per_article:.1f}")
            print(f"Coverage Rate: {coverage_rate:.1f}%")

        if self.stats["processing_time"] > 0:
            rate = self.stats["articles_processed"] / self.stats["processing_time"]
            print(f"Processing Rate: {rate:.1f} articles/second")

        print(f"{'='*60}")

    def get_linking_stats(self) -> dict:
        """Get current article-ticker linking statistics."""
        try:
            # Total articles
            total_articles = self.db.query(Article).count()

            # Articles with ticker links
            articles_with_links = self.db.execute(
                text("SELECT COUNT(DISTINCT article_id) FROM article_ticker")
            ).scalar()

            # Total ticker links
            total_links = self.db.query(ArticleTicker).count()

            # Top linked tickers
            top_tickers = (
                self.db.query(
                    ArticleTicker.ticker, func.count(ArticleTicker.article_id)
                )
                .group_by(ArticleTicker.ticker)
                .order_by(func.count(ArticleTicker.article_id).desc())
                .limit(10)
                .all()
            )

            return {
                "total_articles": total_articles,
                "articles_with_links": articles_with_links,
                "total_links": total_links,
                "coverage_percentage": (
                    (articles_with_links / total_articles * 100)
                    if total_articles > 0
                    else 0
                ),
                "avg_links_per_article": (
                    (total_links / articles_with_links)
                    if articles_with_links > 0
                    else 0
                ),
                "top_tickers": top_tickers,
            }

        except Exception as e:
            logger.error(f"Failed to get linking stats: {e}")
            return {}

    def close(self):
        """Close database connection."""
        self.db.close()


def main():
    """Main function for article re-linking."""
    import sys

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    # Check for command line arguments
    auto_confirm = len(sys.argv) > 1 and sys.argv[1] == "--yes"
    limit = None

    # Check for limit argument
    if len(sys.argv) > 2 and sys.argv[2].startswith("--limit="):
        try:
            limit = int(sys.argv[2].split("=")[1])
        except ValueError:
            print("Invalid limit value. Using no limit.")

    service = ArticleRelinkingService()

    try:
        # Show current stats
        logger.info("Current linking statistics:")
        current_stats = service.get_linking_stats()

        if current_stats:
            print("\nCURRENT STATE:")
            print(f"  Total Articles: {current_stats['total_articles']:,}")
            print(f"  Articles with Links: {current_stats['articles_with_links']:,}")
            print(f"  Total Links: {current_stats['total_links']:,}")
            print(f"  Coverage: {current_stats['coverage_percentage']:.1f}%")
            print(
                f"  Avg Links per Article: {current_stats['avg_links_per_article']:.1f}"
            )

            if current_stats["top_tickers"]:
                print("\nTop Linked Tickers:")
                for ticker, count in current_stats["top_tickers"][:5]:
                    print(f"    {ticker}: {count:,} articles")

        if not auto_confirm:
            # Ask for confirmation
            print("\nThis will re-link ALL articles with the expanded ticker database.")
            print("Existing ticker links will be replaced with new ones.")
            print("To auto-confirm, run with --yes flag")
            return

        print("\n🔄 Starting re-linking process...")
        if limit:
            print(f"   Processing limit: {limit:,} articles")

        # Start re-linking process
        result = service.relink_all_articles(
            batch_size=100,
            limit=limit,  # Process all articles or limited
            clear_existing=True,
        )

        # Show final stats
        if not result.get("error"):
            logger.info("\nFinal linking statistics:")
            final_stats = service.get_linking_stats()

            if final_stats:
                print("\nFINAL STATE:")
                print(f"  Total Articles: {final_stats['total_articles']:,}")
                print(f"  Articles with Links: {final_stats['articles_with_links']:,}")
                print(f"  Total Links: {final_stats['total_links']:,}")
                print(f"  Coverage: {final_stats['coverage_percentage']:.1f}%")
                print(
                    f"  Avg Links per Article: {final_stats['avg_links_per_article']:.1f}"
                )
        else:
            logger.error(f"Re-linking failed: {result['error']}")

    finally:
        service.close()


if __name__ == "__main__":
    main()
