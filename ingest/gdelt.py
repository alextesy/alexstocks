"""GDELT data ingestion CLI script."""

import argparse
import logging
import sys
from datetime import UTC, datetime, timedelta
from urllib.parse import urljoin

import httpx
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import Article, ArticleTicker, Ticker
from app.db.session import SessionLocal
from app.services.sentiment import get_sentiment_service
from ingest.linker import TickerLinker
from ingest.parser import parse_gdelt_export_csv

logger = logging.getLogger(__name__)

# GDELT base URLs
GDELT_BASE_URL = "https://data.gdeltproject.org/gdeltv2/"
GDELT_EXPORT_URL = "https://data.gdeltproject.org/gdeltv2/"


def setup_logging(verbose: bool = False) -> None:
    """Setup logging configuration.

    Args:
        verbose: Enable verbose logging
    """
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )


def get_gdelt_export_urls(hours_back: int = 24) -> list[str]:
    """Get GDELT export URLs for the specified time period.

    Args:
        hours_back: Number of hours to look back

    Returns:
        List of GDELT export URLs
    """
    urls = []
    now = datetime.now(UTC)

    # GDELT export files are generated in 15-minute intervals
    # We'll fetch every 15 minutes for the specified period
    for i in range(hours_back * 4):  # 4 intervals per hour
        target_time = now - timedelta(minutes=i * 15)

        # Round down to the nearest 15-minute interval
        minutes = (target_time.minute // 15) * 15
        target_time = target_time.replace(minute=minutes, second=0, microsecond=0)

        # Format: YYYYMMDDHHMMSS.export.CSV.zip
        time_str = target_time.strftime("%Y%m%d%H%M%S")
        url = urljoin(GDELT_EXPORT_URL, f"{time_str}.export.CSV.zip")
        urls.append(url)

    return urls


def fetch_gdelt_file(url: str, timeout: int = 30) -> str | None:
    """Fetch GDELT file content.

    Args:
        url: GDELT file URL
        timeout: Request timeout in seconds

    Returns:
        File content as string or None if failed
    """
    import zipfile
    import io
    
    try:
        # GDELT servers sometimes have SSL certificate issues, so we'll verify=False
        with httpx.Client(timeout=timeout, verify=False) as client:
            response = client.get(url)
            response.raise_for_status()
            
            # Handle ZIP files
            if url.endswith('.zip'):
                with zipfile.ZipFile(io.BytesIO(response.content)) as zip_file:
                    # Get the first CSV file from the ZIP
                    csv_files = [f for f in zip_file.namelist() if f.endswith('.CSV')]
                    if csv_files:
                        return zip_file.read(csv_files[0]).decode('utf-8')
                    else:
                        logger.warning(f"No CSV files found in ZIP: {url}")
                        return None
            else:
                return response.text
                
    except httpx.HTTPError as e:
        logger.warning(f"Failed to fetch {url}: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error fetching {url}: {e}")
        return None


def load_tickers(db: Session) -> list[Ticker]:
    """Load all tickers from database.

    Args:
        db: Database session

    Returns:
        List of Ticker models
    """
    result = db.execute(select(Ticker))
    return list(result.scalars().all())


def upsert_article(db: Session, article: Article) -> Article | None:
    """Upsert article with URL uniqueness.

    Args:
        db: Database session
        article: Article model instance

    Returns:
        Existing or newly created Article instance
    """
    try:
        # Check if article with this URL already exists
        existing = db.execute(
            select(Article).where(Article.url == article.url)
        ).scalar_one_or_none()

        if existing:
            logger.debug(f"Article already exists: {article.url}")
            return existing

        # Add new article
        db.add(article)
        db.flush()  # Get the ID
        return article

    except IntegrityError as e:
        logger.warning(f"Integrity error for article {article.url}: {e}")
        db.rollback()
        return None
    except Exception as e:
        logger.error(f"Error upserting article {article.url}: {e}")
        db.rollback()
        return None


def save_article_tickers(
    db: Session, article: Article, article_tickers: list[ArticleTicker]
) -> None:
    """Save article-ticker relationships.

    Args:
        db: Database session
        article: Article model instance
        article_tickers: List of ArticleTicker relationships
    """
    try:
        # Deduplicate relationships by (article_id, ticker) pair
        unique_relationships = {}
        for article_ticker in article_tickers:
            article_ticker.article_id = article.id
            key = (article_ticker.article_id, article_ticker.ticker)
            if key not in unique_relationships:
                unique_relationships[key] = article_ticker

        # Add unique relationships only
        db.add_all(unique_relationships.values())

    except Exception as e:
        logger.error(f"Error saving article-ticker relationships: {e}")
        db.rollback()


def ingest_gdelt_data(hours_back: int = 24, verbose: bool = False, max_workers: int = 10) -> None:
    """Ingest GDELT data for the specified time period.

    Args:
        hours_back: Number of hours to look back
        verbose: Enable verbose logging
        max_workers: Maximum number of concurrent scraping threads
    """
    setup_logging(verbose)

    logger.info(f"Starting GDELT ingestion for last {hours_back} hours")

    # Get database session
    db = SessionLocal()
    try:
        # Load tickers
        logger.info("Loading tickers from database")
        tickers = load_tickers(db)
        if not tickers:
            logger.error("No tickers found in database. Run seed-tickers first.")
            return

        logger.info(f"Loaded {len(tickers)} tickers")

        # Initialize ticker linker and sentiment service
        linker = TickerLinker(tickers, max_scraping_workers=max_workers)
        sentiment_service = get_sentiment_service()

        # Get GDELT URLs
        urls = get_gdelt_export_urls(hours_back)
        logger.info(f"Fetching {len(urls)} GDELT files")

        total_articles = 0
        total_links = 0

        # Process each URL
        for i, url in enumerate(urls, 1):
            logger.info(f"Processing file {i}/{len(urls)}: {url}")

            # Fetch file content
            content = fetch_gdelt_file(url)
            if not content:
                logger.warning(f"Skipping file {url}")
                continue

            # Parse articles (using export format parser)
            articles = parse_gdelt_export_csv(content)
            if not articles:
                logger.warning(f"No articles parsed from {url}")
                continue

            logger.info(f"Parsed {len(articles)} articles from {url}")

            # Link articles to tickers with multithreaded scraping
            linked_articles = linker.link_articles_to_db_with_multithreaded_scraping(articles)

            # Save to database
            file_articles = 0
            file_links = 0

            for article, article_tickers in linked_articles:
                # Upsert article
                saved_article = upsert_article(db, article)
                if not saved_article:
                    continue

                file_articles += 1

                # Save article-ticker relationships
                if article_tickers:
                    save_article_tickers(db, saved_article, article_tickers)
                    file_links += len(article_tickers)
                    file_links += len(article_tickers)

            # Commit batch
            try:
                db.commit()
                logger.info(
                    f"Saved {file_articles} articles with {file_links} ticker links"
                )
                total_articles += file_articles
                total_links += file_links
            except Exception as e:
                logger.error(f"Error committing batch: {e}")
                db.rollback()

        logger.info(
            f"Ingestion complete: {total_articles} articles, {total_links} ticker links"
        )

    except Exception as e:
        logger.error(f"Unexpected error during ingestion: {e}")
        db.rollback()
    finally:
        db.close()


def main() -> None:
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(description="GDELT data ingestion CLI")
    parser.add_argument(
        "--hours",
        type=int,
        default=24,
        help="Number of hours to look back (default: 24)",
    )
    parser.add_argument("--verbose", action="store_true", help="Enable verbose logging")
    parser.add_argument(
        "--workers",
        type=int,
        default=10,
        help="Number of concurrent scraping threads (default: 10)",
    )

    args = parser.parse_args()

    try:
        ingest_gdelt_data(hours_back=args.hours, verbose=args.verbose, max_workers=args.workers)
    except KeyboardInterrupt:
        logger.info("Ingestion interrupted by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
