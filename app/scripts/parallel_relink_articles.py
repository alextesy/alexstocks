"""Parallel re-linking of articles to tickers using multiprocessing."""

import logging
import multiprocessing as mp
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from typing import Any

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from tqdm import tqdm

from app.config import settings
from app.db.models import Article, ArticleTicker, Ticker
from ingest.linker import TickerLinker

logger = logging.getLogger(__name__)


def setup_worker_db():
    """Set up database connection for worker processes."""
    # Import settings in worker to avoid pickling issues

    engine = create_engine(
        str(settings.postgres_url), pool_pre_ping=True, pool_recycle=3600, echo=False
    )
    Session = sessionmaker(bind=engine)
    return Session


def process_article_batch(batch_data: tuple[list[dict], list[dict], int]) -> dict:
    """Process a batch of articles in a worker process.

    Args:
        batch_data: Tuple of (article_data_list, ticker_data_list, worker_id)

    Returns:
        Dictionary with processing results
    """
    article_data_list, ticker_data_list, worker_id = batch_data

    # Set up logging for this worker
    logging.basicConfig(level=logging.WARNING)  # Reduce noise
    worker_logger = logging.getLogger(f"worker_{worker_id}")

    # Create database session for this worker
    Session = setup_worker_db()
    db = Session()

    try:
        # Reconstruct ticker objects for this worker
        tickers: list[Ticker] = []
        for ticker_data in ticker_data_list:
            ticker = Ticker(
                symbol=ticker_data["symbol"],
                name=ticker_data["name"],
                aliases=ticker_data["aliases"],
                exchange=ticker_data.get("exchange"),
                sources=ticker_data.get("sources", []),
                is_sp500=ticker_data.get("is_sp500", False),
                cik=ticker_data.get("cik"),
            )
            tickers.append(ticker)

        # Initialize ticker linker for this worker
        ticker_linker = TickerLinker(
            tickers, max_scraping_workers=2
        )  # Reduce per-worker threads

        worker_stats: dict[str, Any] = {
            "worker_id": worker_id,
            "articles_processed": 0,
            "articles_with_links": 0,
            "total_links_removed": 0,
            "total_links_added": 0,
            "errors": [],
        }

        # Process each article in the batch with progress bar
        with tqdm(
            total=len(article_data_list),
            desc=f"Worker {worker_id}",
            unit="article",
            position=worker_id,
            leave=False,
            bar_format="{desc}: {percentage:3.0f}%|{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}]",
        ) as pbar:

            for article_data in article_data_list:
                try:
                    # Reconstruct article object
                    article = Article(
                        id=article_data["id"],
                        title=article_data["title"],
                        text=article_data["text"],
                        url=article_data["url"],
                        published_at=article_data["published_at"],
                        source=article_data["source"],
                    )

                    # Clear existing links
                    existing_links = (
                        db.query(ArticleTicker)
                        .filter(ArticleTicker.article_id == article.id)
                        .all()
                    )

                    links_removed = len(existing_links)
                    for link in existing_links:
                        db.delete(link)

                    # Find new ticker links
                    ticker_links = ticker_linker.link_article(
                        article, use_title_only=True
                    )

                    # Create new ArticleTicker relationships
                    for ticker_link in ticker_links:
                        article_ticker = ArticleTicker(
                            article_id=article.id,
                            ticker=ticker_link.ticker,
                            confidence=ticker_link.confidence,
                            matched_terms=ticker_link.matched_terms,
                        )
                        db.add(article_ticker)

                    # Commit changes for this article
                    db.commit()

                    # Update stats
                    worker_stats["articles_processed"] += 1
                    worker_stats["total_links_removed"] += links_removed
                    worker_stats["total_links_added"] += len(ticker_links)

                    if len(ticker_links) > 0:
                        worker_stats["articles_with_links"] += 1

                    # Update progress bar
                    pbar.set_postfix(
                        {
                            "links": f"{len(ticker_links)}",
                            "total": f"{worker_stats['total_links_added']}",
                        }
                    )
                    pbar.update(1)

                except Exception as e:
                    error_msg = f"Worker {worker_id} failed to process article {article_data['id']}: {e}"
                    worker_stats["errors"].append(error_msg)
                    worker_logger.error(error_msg)
                    db.rollback()
                    pbar.update(1)

        return worker_stats

    except Exception as e:
        error_msg = f"Worker {worker_id} failed: {e}"
        return {
            "worker_id": worker_id,
            "articles_processed": 0,
            "articles_with_links": 0,
            "total_links_removed": 0,
            "total_links_added": 0,
            "errors": [error_msg],
        }
    finally:
        db.close()


class ParallelArticleRelinkingService:
    """Parallel service to re-link articles with multiprocessing."""

    def __init__(self, max_workers: int | None = None):
        self.max_workers = max_workers or max(1, mp.cpu_count() - 1)
        self.stats: dict[str, Any] = {
            "articles_processed": 0,
            "articles_with_links": 0,
            "total_links_removed": 0,
            "total_links_added": 0,
            "errors": [],
            "processing_time": 0.0,
        }

        # Set up main database connection
        from app.db.session import SessionLocal

        self.db = SessionLocal()

    def get_articles_batch_data(
        self, limit: int | None = None, batch_size: int = 50
    ) -> list[list[dict]]:
        """Get article data in batches for parallel processing."""
        logger.info("Loading articles for parallel processing...")

        query = self.db.query(Article).order_by(Article.published_at.desc())

        if limit:
            query = query.limit(limit)

        articles = query.all()

        # Convert to serializable data
        article_data_list = []
        for article in articles:
            article_data = {
                "id": article.id,
                "title": article.title,
                "text": article.text,
                "url": article.url,
                "published_at": article.published_at,
                "source": article.source,
            }
            article_data_list.append(article_data)

        # Split into batches
        batches = []
        for i in range(0, len(article_data_list), batch_size):
            batch = article_data_list[i : i + batch_size]
            batches.append(batch)

        logger.info(f"Created {len(batches)} batches of ~{batch_size} articles each")
        return batches

    def get_ticker_data(self) -> list[dict]:
        """Get ticker data for workers."""
        logger.info("Loading ticker data for workers...")

        tickers = self.db.query(Ticker).all()

        ticker_data_list = []
        for ticker in tickers:
            ticker_data = {
                "symbol": ticker.symbol,
                "name": ticker.name,
                "aliases": ticker.aliases,
                "exchange": ticker.exchange,
                "sources": ticker.sources,
                "is_sp500": ticker.is_sp500,
                "cik": ticker.cik,
            }
            ticker_data_list.append(ticker_data)

        logger.info(f"Loaded {len(ticker_data_list)} tickers for workers")
        return ticker_data_list

    def parallel_relink_articles(
        self, limit: int | None = None, batch_size: int = 50
    ) -> dict:
        """Re-link articles using parallel processing."""
        print(f"\n🚀 Starting parallel re-linking with {self.max_workers} workers...")
        start_time = time.time()

        # Get data for workers
        print("📊 Loading articles and ticker data...")
        article_batches = self.get_articles_batch_data(limit, batch_size)
        ticker_data = self.get_ticker_data()

        total_articles = sum(len(batch) for batch in article_batches)
        print(
            f"✅ Ready to process {total_articles:,} articles in {len(article_batches)} batches"
        )
        print(f"⚡ Expected speedup: ~{self.max_workers}x faster than sequential")
        print()

        # Prepare batch data for workers
        batch_data_list = []
        for i, article_batch in enumerate(article_batches):
            batch_data = (article_batch, ticker_data, i)
            batch_data_list.append(batch_data)

        # Process batches in parallel with progress bar
        with ProcessPoolExecutor(max_workers=self.max_workers) as executor:
            # Submit all jobs
            future_to_batch = {
                executor.submit(process_article_batch, batch_data): i
                for i, batch_data in enumerate(batch_data_list)
            }

            # Create progress bar
            with tqdm(
                total=len(article_batches),
                desc="Processing batches",
                unit="batch",
                bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} batches [{elapsed}<{remaining}, {rate_fmt}]",
            ) as pbar:

                # Process completed jobs
                for future in as_completed(future_to_batch):
                    batch_idx = future_to_batch[future]

                    try:
                        worker_result = future.result()

                        # Aggregate stats
                        self.stats["articles_processed"] += worker_result[
                            "articles_processed"
                        ]
                        self.stats["articles_with_links"] += worker_result[
                            "articles_with_links"
                        ]
                        self.stats["total_links_removed"] += worker_result[
                            "total_links_removed"
                        ]
                        self.stats["total_links_added"] += worker_result[
                            "total_links_added"
                        ]
                        self.stats["errors"].extend(worker_result["errors"])

                        # Update progress bar with detailed info
                        elapsed = time.time() - start_time
                        rate = float(
                            self.stats["articles_processed"] / elapsed
                            if elapsed > 0
                            else 0
                        )

                        pbar.set_postfix(
                            {
                                "articles": f"{self.stats['articles_processed']:,}/{total_articles:,}",
                                "rate": f"{rate:.1f}/s",
                                "links": f"{self.stats['total_links_added']:,}",
                                "errors": len(self.stats["errors"]),
                            }
                        )
                        pbar.update(1)

                    except Exception as e:
                        error_msg = f"Batch {batch_idx} failed: {e}"
                        self.stats["errors"].append(error_msg)
                        logger.error(error_msg)
                        pbar.update(1)

        self.stats["processing_time"] = time.time() - start_time

        logger.info("Parallel re-linking completed!")
        self.print_summary()

        return self.stats

    def print_summary(self):
        """Print summary of re-linking process."""
        print(f"\n{'='*80}")
        print("PARALLEL ARTICLE RE-LINKING SUMMARY")
        print(f"{'='*80}")
        print(f"Workers Used: {self.max_workers}")
        print(f"Articles Processed: {self.stats['articles_processed']:,}")
        print(f"Articles with New Links: {self.stats['articles_with_links']:,}")
        print(f"Total Links Removed: {self.stats['total_links_removed']:,}")
        print(f"Total Links Added: {self.stats['total_links_added']:,}")
        print(f"Processing Time: {self.stats['processing_time']:.1f} seconds")

        if self.stats["articles_processed"] and self.stats["articles_processed"] > 0:
            coverage_rate = float(
                (self.stats["articles_with_links"] / self.stats["articles_processed"])
                * 100
            )
            avg_links_per_article = float(
                self.stats["total_links_added"] / self.stats["articles_processed"]
            )

            print(f"Coverage Rate: {coverage_rate:.1f}%")
            print(f"Average Links per Article: {avg_links_per_article:.1f}")

        if self.stats["processing_time"] and self.stats["processing_time"] > 0:
            rate = float(
                self.stats["articles_processed"] / self.stats["processing_time"]
            )
            speedup = float(
                rate / 0.2
            )  # Compare to sequential rate of 0.2 articles/sec
            print(f"Processing Rate: {rate:.1f} articles/second")
            print(f"Speedup vs Sequential: {speedup:.1f}x")

        if self.stats["errors"]:
            print(f"Errors: {len(self.stats['errors'])}")
            print("First few errors:")
            for error in self.stats["errors"][:3]:
                print(f"  - {error}")

        print(f"{'='*80}")

    def get_linking_stats(self) -> dict:
        """Get current article-ticker linking statistics."""
        try:
            from sqlalchemy import func, text

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
                    float(articles_with_links / total_articles * 100)
                    if total_articles
                    and articles_with_links is not None
                    and total_articles > 0
                    else 0
                ),
                "avg_links_per_article": (
                    float(total_links / articles_with_links)
                    if articles_with_links and articles_with_links > 0
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
    """Main function for parallel article re-linking."""
    import sys

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    # Parse command line arguments
    auto_confirm = "--yes" in sys.argv
    limit = None
    workers = None
    batch_size = 50

    for arg in sys.argv[1:]:
        if arg.startswith("--limit="):
            try:
                limit = int(arg.split("=")[1])
            except ValueError:
                print("Invalid limit value.")
                return
        elif arg.startswith("--workers="):
            try:
                workers = int(arg.split("=")[1])
            except ValueError:
                print("Invalid workers value.")
                return
        elif arg.startswith("--batch-size="):
            try:
                batch_size = int(arg.split("=")[1])
            except ValueError:
                print("Invalid batch-size value.")
                return

    service = ParallelArticleRelinkingService(max_workers=workers)

    try:
        # Show current stats
        print("Current linking statistics:")
        current_stats = service.get_linking_stats()

        if current_stats:
            print("\nCURRENT STATE:")
            print(f"  Total Articles: {current_stats['total_articles']:,}")
            print(f"  Articles with Links: {current_stats['articles_with_links']:,}")
            print(f"  Total Links: {current_stats['total_links']:,}")
            print(f"  Coverage: {current_stats['coverage_percentage']:.1f}%")

            if current_stats["top_tickers"]:
                print("\nTop Linked Tickers:")
                for ticker, count in current_stats["top_tickers"][:5]:
                    print(f"    {ticker}: {count:,} articles")

        print("\nParallel Processing Configuration:")
        print(f"  Workers: {service.max_workers}")
        print(f"  Batch size: {batch_size}")
        print(f"  Expected speedup: ~{service.max_workers}x")

        if not auto_confirm:
            print("\nThis will re-link articles with the expanded ticker database.")
            print(
                "Usage: python parallel_relink_articles.py --yes [--limit=N] [--workers=N] [--batch-size=N]"
            )
            return

        print("\n🚀 Starting parallel re-linking...")
        if limit:
            print(f"   Processing limit: {limit:,} articles")

        # Start parallel re-linking
        result = service.parallel_relink_articles(limit=limit, batch_size=batch_size)

        # Show final stats
        if not result.get("errors") or len(result["errors"]) == 0:
            print("\n✅ Re-linking completed successfully!")

            final_stats = service.get_linking_stats()
            if final_stats:
                print("\nFINAL STATE:")
                print(f"  Total Articles: {final_stats['total_articles']:,}")
                print(f"  Articles with Links: {final_stats['articles_with_links']:,}")
                print(f"  Total Links: {final_stats['total_links']:,}")
                print(f"  Coverage: {final_stats['coverage_percentage']:.1f}%")
        else:
            print(f"⚠️  Re-linking completed with {len(result['errors'])} errors")

    finally:
        service.close()


if __name__ == "__main__":
    main()
