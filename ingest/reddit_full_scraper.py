"""Adhoc Reddit full thread scraper for complete comment extraction."""

import argparse
import logging
import sys
import time
from datetime import UTC, datetime
from typing import Any, Dict, List, Optional, Tuple

import praw
from dotenv import load_dotenv
from praw.models import Comment, Submission
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import Article, ArticleTicker, RedditThread, Ticker
from app.db.session import SessionLocal
from ingest.linker import TickerLinker
from ingest.reddit import get_reddit_credentials
from ingest.reddit_discussion_scraper import RedditDiscussionScraper

# Load environment variables from .env file
load_dotenv()

logger = logging.getLogger(__name__)


class RedditFullScraper:
    """Full Reddit thread scraper that gets ALL comments including nested replies."""

    def __init__(self, max_scraping_workers: int = 5):
        """Initialize the full scraper.

        Args:
            max_scraping_workers: Maximum number of workers for ticker linking
        """
        self.discussion_scraper = RedditDiscussionScraper()
        self.max_scraping_workers = max_scraping_workers
        self.reddit: Optional[praw.Reddit] = None

    def initialize_reddit(
        self, client_id: str, client_secret: str, user_agent: str
    ) -> None:
        """Initialize the PRAW Reddit instance.

        Args:
            client_id: Reddit API client ID
            client_secret: Reddit API client secret
            user_agent: Custom user agent string
        """
        self.discussion_scraper.initialize_reddit(client_id, client_secret, user_agent)
        self.reddit = self.discussion_scraper.reddit

    def extract_all_comments_from_thread(
        self, submission: Submission, max_replace_more: int = None
    ) -> List[Comment]:
        """Extract ALL comments from a thread including nested replies.

        Args:
            submission: Reddit submission
            max_replace_more: Maximum "more comments" to expand (None = no limit)

        Returns:
            List of ALL comments from the thread
        """
        if not self.reddit:
            raise RuntimeError("Reddit instance not initialized.")

        logger.info(f"Starting full extraction for thread: {submission.title}")
        logger.info(f"Thread has {submission.num_comments} total comments")

        try:
            start_time = time.time()
            
            # Expand ALL "more comments" if no limit specified
            if max_replace_more is None:
                logger.info("Expanding ALL 'more comments' (no limit)...")
                submission.comments.replace_more(limit=None)
            else:
                logger.info(f"Expanding up to {max_replace_more} 'more comments'...")
                submission.comments.replace_more(limit=max_replace_more)
            
            # Get flattened list of ALL comments
            all_comments = submission.comments.list()
            
            # Filter out deleted/removed comments
            valid_comments = []
            for comment in all_comments:
                if comment.body not in ["[deleted]", "[removed]"]:
                    valid_comments.append(comment)

            elapsed_time = time.time() - start_time
            logger.info(f"Extracted {len(valid_comments)} valid comments out of {len(all_comments)} total in {elapsed_time:.2f}s")
            
            return valid_comments

        except Exception as e:
            logger.error(f"Error extracting all comments: {e}")
            return []

    def get_existing_comment_ids(self, db: Session, thread_id: str) -> set[str]:
        """Get set of already scraped comment IDs for a thread.

        Args:
            db: Database session
            thread_id: Reddit thread ID

        Returns:
            Set of existing comment IDs
        """
        result = db.execute(
            select(Article.reddit_id).where(
                Article.source == "reddit_comment",
                Article.reddit_url.like(f"%{thread_id}%")
            )
        )
        return {row[0] for row in result if row[0]}

    def scrape_thread_completely(
        self,
        db: Session,
        submission: Submission,
        tickers: List[Ticker],
        max_replace_more: int = None,
        skip_existing: bool = True,
    ) -> Dict[str, Any]:
        """Scrape a thread completely, getting all comments.

        Args:
            db: Database session
            submission: Reddit submission
            tickers: List of tickers for linking
            max_replace_more: Maximum "more comments" to expand (None = unlimited)
            skip_existing: Skip comments already in database

        Returns:
            Dictionary with scraping statistics
        """
        try:
            logger.info(f"Starting complete scrape of thread: {submission.title}")
            
            # Get or create thread record
            existing_thread = db.execute(
                select(RedditThread).where(RedditThread.reddit_id == submission.id)
            ).scalar_one_or_none()

            if existing_thread:
                thread_record = existing_thread
                logger.info(f"Found existing thread record with {thread_record.scraped_comments} scraped comments")
            else:
                # Determine thread type
                title_lower = submission.title.lower()
                if "daily discussion" in title_lower:
                    thread_type = "daily"
                elif "weekend discussion" in title_lower:
                    thread_type = "weekend"
                else:
                    thread_type = "other"

                # Create new thread record
                thread_record = RedditThread(
                    reddit_id=submission.id,
                    subreddit=submission.subreddit.display_name,
                    title=submission.title,
                    thread_type=thread_type,
                    url=f"https://www.reddit.com{submission.permalink}",
                    author=submission.author.name if submission.author else "[deleted]",
                    upvotes=submission.score,
                    total_comments=submission.num_comments,
                    scraped_comments=0,
                    is_complete=False,
                )
                db.add(thread_record)
                db.flush()
                logger.info("Created new thread record")

            # Get existing comment IDs if skipping
            existing_comment_ids = set()
            if skip_existing:
                existing_comment_ids = self.get_existing_comment_ids(db, submission.id)
                logger.info(f"Found {len(existing_comment_ids)} existing comments in database")

            # Extract ALL comments
            all_comments = self.extract_all_comments_from_thread(submission, max_replace_more)

            if not all_comments:
                logger.warning("No comments extracted from thread")
                return {"total_comments": 0, "new_comments": 0, "processed_articles": 0, "ticker_links": 0}

            # Filter out existing comments if skipping
            new_comments = []
            if skip_existing:
                for comment in all_comments:
                    if comment.id not in existing_comment_ids:
                        new_comments.append(comment)
                logger.info(f"Found {len(new_comments)} new comments to process (skipping {len(all_comments) - len(new_comments)} existing)")
            else:
                new_comments = all_comments
                logger.info(f"Processing all {len(new_comments)} comments (not skipping existing)")

            if not new_comments:
                logger.info("No new comments to process")
                thread_record.last_scraped_at = datetime.now(UTC)
                return {"total_comments": len(all_comments), "new_comments": 0, "processed_articles": 0, "ticker_links": 0}

            # Initialize ticker linker
            linker = TickerLinker(tickers, max_scraping_workers=self.max_scraping_workers)

            # Process comments in batches for better performance
            batch_size = 100
            processed_articles = 0
            total_ticker_links = 0
            processed_count = 0

            logger.info(f"Processing {len(new_comments)} comments in batches of {batch_size}")

            for i in range(0, len(new_comments), batch_size):
                batch = new_comments[i:i + batch_size]
                batch_num = (i // batch_size) + 1
                total_batches = (len(new_comments) + batch_size - 1) // batch_size
                
                logger.info(f"Processing batch {batch_num}/{total_batches} ({len(batch)} comments)")

                for comment in batch:
                    try:
                        # Parse comment to article
                        article = self.discussion_scraper.parse_comment_to_article(comment, submission)
                        
                        # Check if article already exists (by reddit_id) if not skipping
                        if not skip_existing:
                            existing_article = db.execute(
                                select(Article).where(Article.reddit_id == article.reddit_id)
                            ).scalar_one_or_none()

                            if existing_article:
                                logger.debug(f"Comment {comment.id} already exists, skipping")
                                continue

                        # Add article to database
                        db.add(article)
                        db.flush()  # Get the ID

                        # Link to tickers
                        ticker_links = linker.link_article(article, use_title_only=True)
                        
                        # Save ticker links
                        for link in ticker_links:
                            article_ticker = ArticleTicker(
                                article_id=article.id,
                                ticker=link.ticker,
                                confidence=link.confidence,
                                matched_terms=link.matched_terms,
                            )
                            db.add(article_ticker)

                        processed_articles += 1
                        total_ticker_links += len(ticker_links)
                        processed_count += 1

                        # Log progress every 50 comments
                        if processed_count % 50 == 0:
                            logger.info(f"Processed {processed_count}/{len(new_comments)} comments...")

                    except IntegrityError as e:
                        logger.warning(f"Integrity error for comment {comment.id}: {e}")
                        db.rollback()
                        continue
                    except Exception as e:
                        logger.error(f"Error processing comment {comment.id}: {e}")
                        continue

                # Commit batch
                try:
                    db.commit()
                    logger.info(f"Committed batch {batch_num}/{total_batches}")
                except Exception as e:
                    logger.error(f"Error committing batch {batch_num}: {e}")
                    db.rollback()

            # Update thread record
            thread_record.scraped_comments = max(thread_record.scraped_comments, len(all_comments))
            thread_record.total_comments = submission.num_comments
            thread_record.last_scraped_at = datetime.now(UTC)
            thread_record.is_complete = True  # Mark as complete since we got all comments
            
            db.commit()

            logger.info(
                f"Complete scrape finished: {len(all_comments)} total comments, "
                f"{len(new_comments)} new comments, {processed_articles} articles processed, "
                f"{total_ticker_links} ticker links"
            )

            return {
                "total_comments": len(all_comments),
                "new_comments": len(new_comments),
                "processed_articles": processed_articles,
                "ticker_links": total_ticker_links,
            }

        except Exception as e:
            logger.error(f"Error in complete thread scraping: {e}")
            return {"total_comments": 0, "new_comments": 0, "processed_articles": 0, "ticker_links": 0}

    def scrape_latest_daily_threads_completely(
        self,
        subreddit_name: str = "wallstreetbets",
        max_threads: int = 1,
        max_replace_more: int = None,
        skip_existing: bool = True,
    ) -> Dict[str, Any]:
        """Scrape latest daily discussion threads completely.

        Args:
            subreddit_name: Name of the subreddit
            max_threads: Maximum number of threads to process
            max_replace_more: Maximum "more comments" to expand per thread (None = unlimited)
            skip_existing: Skip comments already in database

        Returns:
            Dictionary with scraping results
        """
        if not self.reddit:
            raise RuntimeError("Reddit instance not initialized.")

        db = SessionLocal()
        try:
            # Load tickers
            tickers = db.execute(select(Ticker)).scalars().all()
            if not tickers:
                logger.error("No tickers found in database")
                return {"error": "No tickers available"}

            # Find discussion threads
            discussion_threads = self.discussion_scraper.find_daily_discussion_threads(
                subreddit_name, limit=50
            )

            if not discussion_threads:
                logger.warning(f"No discussion threads found in r/{subreddit_name}")
                return {"error": "No discussion threads found"}

            # Process threads (prioritize newest ones)
            processed_threads = discussion_threads[:max_threads]
            total_stats = {
                "threads_processed": 0,
                "total_comments": 0,
                "total_new_comments": 0,
                "total_articles": 0,
                "total_ticker_links": 0,
            }

            for i, thread in enumerate(processed_threads, 1):
                logger.info(f"Processing thread {i}/{len(processed_threads)}: {thread.title}")

                thread_stats = self.scrape_thread_completely(
                    db, thread, tickers, max_replace_more, skip_existing
                )

                # Update totals
                total_stats["threads_processed"] += 1
                total_stats["total_comments"] += thread_stats["total_comments"]
                total_stats["total_new_comments"] += thread_stats["new_comments"]
                total_stats["total_articles"] += thread_stats["processed_articles"]
                total_stats["total_ticker_links"] += thread_stats["ticker_links"]

            logger.info(
                f"Full scrape complete: {total_stats['threads_processed']} threads, "
                f"{total_stats['total_comments']} total comments, "
                f"{total_stats['total_new_comments']} new comments, "
                f"{total_stats['total_articles']} articles, "
                f"{total_stats['total_ticker_links']} ticker links"
            )

            return total_stats

        except Exception as e:
            logger.error(f"Error in full thread scrape: {e}")
            db.rollback()
            return {"error": str(e)}
        finally:
            db.close()


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


def run_full_scrape(
    subreddit: str = "wallstreetbets",
    max_threads: int = 1,
    max_replace_more: Optional[int] = None,
    max_workers: int = 5,
    skip_existing: bool = True,
    verbose: bool = False,
) -> None:
    """Run full Reddit thread scraping.

    Args:
        subreddit: Subreddit to scrape
        max_threads: Maximum number of threads to process
        max_replace_more: Maximum "more comments" to expand (None = unlimited)
        max_workers: Maximum number of workers for ticker linking
        skip_existing: Skip comments already in database
        verbose: Enable verbose logging
    """
    setup_logging(verbose)
    logger.info(f"Starting FULL Reddit scraping for r/{subreddit}")
    
    if max_replace_more is None:
        logger.warning("⚠️  No limit on 'more comments' expansion - this may take a VERY long time!")
    else:
        logger.info(f"Will expand up to {max_replace_more} 'more comments' per thread")

    try:
        # Get Reddit credentials
        client_id, client_secret, user_agent = get_reddit_credentials()
    except ValueError as e:
        logger.error(f"Skipping Reddit scraping due to missing credentials: {e}")
        return

    try:
        # Initialize scraper
        scraper = RedditFullScraper(max_scraping_workers=max_workers)
        scraper.initialize_reddit(client_id, client_secret, user_agent)

        # Run full scrape
        results = scraper.scrape_latest_daily_threads_completely(
            subreddit_name=subreddit,
            max_threads=max_threads,
            max_replace_more=max_replace_more,
            skip_existing=skip_existing,
        )

        if "error" in results:
            logger.error(f"Scraping failed: {results['error']}")
            sys.exit(1)

        # Log results
        logger.info("🎉 FULL scraping completed successfully:")
        logger.info(f"  Threads processed: {results['threads_processed']}")
        logger.info(f"  Total comments found: {results['total_comments']}")
        logger.info(f"  New comments scraped: {results['total_new_comments']}")
        logger.info(f"  Articles created: {results['total_articles']}")
        logger.info(f"  Ticker links: {results['total_ticker_links']}")

        print("✅ Full Reddit thread scraping completed successfully")

    except Exception as e:
        logger.error(f"Fatal error during full scraping: {e}")
        sys.exit(1)


def main() -> None:
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(description="Full Reddit thread scraping CLI")
    
    parser.add_argument(
        "--subreddit",
        type=str,
        default="wallstreetbets",
        help="Subreddit to scrape (default: wallstreetbets)",
    )
    parser.add_argument(
        "--max-threads",
        type=int,
        default=1,
        help="Maximum number of threads to process (default: 1)",
    )
    parser.add_argument(
        "--max-replace-more",
        type=int,
        default=None,
        help="Maximum 'more comments' to expand (default: unlimited - WARNING: very slow!)",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=5,
        help="Number of concurrent workers (default: 5)",
    )
    parser.add_argument(
        "--include-existing",
        action="store_true",
        help="Include comments already in database (default: skip existing)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose logging",
    )

    args = parser.parse_args()

    run_full_scrape(
        subreddit=args.subreddit,
        max_threads=args.max_threads,
        max_replace_more=args.max_replace_more,
        max_workers=args.workers,
        skip_existing=not args.include_existing,
        verbose=args.verbose,
    )


if __name__ == "__main__":
    main()
