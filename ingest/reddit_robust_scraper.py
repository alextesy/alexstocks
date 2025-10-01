"""Robust Reddit scraper with rate limit handling and incremental saving."""

import argparse
import logging
import sys
import time
from datetime import UTC, datetime
from typing import Any

import praw
from dotenv import load_dotenv
from praw.models import Comment, Submission
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.db.models import Article, ArticleTicker, RedditThread, Ticker
from app.db.session import SessionLocal
from ingest.linker import TickerLinker
from ingest.reddit import get_reddit_credentials
from ingest.reddit_discussion_scraper import RedditDiscussionScraper

# Load environment variables from .env file
load_dotenv()

logger = logging.getLogger(__name__)


class RedditRobustScraper:
    """Robust Reddit scraper with rate limit handling and incremental saving."""

    def __init__(self, max_scraping_workers: int = 5):
        """Initialize the robust scraper.

        Args:
            max_scraping_workers: Maximum number of workers for ticker linking
        """
        self.discussion_scraper = RedditDiscussionScraper()
        self.max_scraping_workers = max_scraping_workers
        self.reddit: praw.Reddit | None = None

        # Rate limiting configuration
        self.requests_per_minute = 90  # Stay under 100 QPM limit
        self.request_times: list[float] = []  # Track request times for rate limiting
        self.batch_save_interval = 200  # Save every 200 comments
        self.rate_limit_sleep = 60  # Sleep 60 seconds on rate limit

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

    def _rate_limit_check(self) -> None:
        """Check and enforce rate limits."""
        current_time = time.time()

        # Remove requests older than 1 minute
        self.request_times = [t for t in self.request_times if current_time - t < 60]

        # If we're approaching the limit, wait
        if len(self.request_times) >= self.requests_per_minute:
            sleep_time = 60 - (current_time - self.request_times[0]) + 1
            if sleep_time > 0:
                logger.info(
                    f"Rate limit approaching, sleeping for {sleep_time:.1f} seconds..."
                )
                time.sleep(sleep_time)
                # Clean up old requests after sleep
                current_time = time.time()
                self.request_times = [
                    t for t in self.request_times if current_time - t < 60
                ]

        # Record this request
        self.request_times.append(current_time)

    def _handle_rate_limit_error(self, error: Exception) -> bool:
        """Handle rate limit errors with exponential backoff.

        Args:
            error: The exception that occurred

        Returns:
            True if we should retry, False if we should give up
        """
        if "429" in str(error) or "rate limit" in str(error).lower():
            logger.warning(f"Rate limit hit: {error}")
            logger.info(f"Sleeping for {self.rate_limit_sleep} seconds...")
            time.sleep(self.rate_limit_sleep)
            return True
        return False

    def extract_comments_with_retry(
        self, submission: Submission, max_replace_more: int | None = None, max_retries: int = 3
    ) -> list[Comment]:
        """Extract comments with rate limit handling and retries.

        Args:
            submission: Reddit submission
            max_replace_more: Maximum "more comments" to expand
            max_retries: Maximum number of retries on rate limit

        Returns:
            List of comments from the thread
        """
        if not self.reddit:
            raise RuntimeError("Reddit instance not initialized.")

        logger.info(f"Starting robust extraction for thread: {submission.title}")
        logger.info(f"Thread has {submission.num_comments} total comments")

        for attempt in range(max_retries + 1):
            try:
                self._rate_limit_check()

                start_time = time.time()

                # Expand "more comments" with rate limit handling
                if max_replace_more is None:
                    logger.info("Expanding ALL 'more comments' (no limit)...")
                    # For large threads, we'll expand in smaller chunks
                    submission.comments.replace_more(limit=None)
                else:
                    logger.info(
                        f"Expanding up to {max_replace_more} 'more comments'..."
                    )
                    submission.comments.replace_more(limit=max_replace_more)

                # Get flattened list of ALL comments
                all_comments = submission.comments.list()

                # Filter out deleted/removed comments
                valid_comments = []
                for comment in all_comments:
                    if comment.body not in ["[deleted]", "[removed]"]:
                        valid_comments.append(comment)

                elapsed_time = time.time() - start_time
                logger.info(
                    f"Extracted {len(valid_comments)} valid comments out of {len(all_comments)} total in {elapsed_time:.2f}s"
                )

                return valid_comments

            except Exception as e:
                if self._handle_rate_limit_error(e) and attempt < max_retries:
                    logger.info(
                        f"Retrying comment extraction (attempt {attempt + 2}/{max_retries + 1})..."
                    )
                    continue
                else:
                    logger.error(
                        f"Error extracting comments after {attempt + 1} attempts: {e}"
                    )
                    return []

        return []

    def scrape_thread_robust(
        self,
        submission: Submission,
        skip_existing: bool = True,
        max_replace_more: int | None = None,
    ) -> dict[str, int]:
        """Scrape a thread with robust error handling and incremental saving.

        Args:
            submission: Reddit submission to scrape
            skip_existing: Whether to skip comments that already exist
            max_replace_more: Maximum "more comments" to expand

        Returns:
            Dictionary with scraping statistics
        """
        db = SessionLocal()
        try:
            # Get or create thread record
            thread_record = db.execute(
                select(RedditThread).where(RedditThread.reddit_id == submission.id)
            ).scalar_one_or_none()

            if not thread_record:
                thread_record = RedditThread(
                    reddit_id=submission.id,
                    title=submission.title,
                    subreddit=submission.subreddit.display_name,
                    thread_type="daily",  # Default to daily, could be improved
                    url=f"https://reddit.com{submission.permalink}",
                    author=submission.author.name if submission.author else None,
                    upvotes=submission.score,
                    total_comments=submission.num_comments,
                    scraped_comments=0,
                    is_complete=False,
                    created_at=datetime.now(UTC),
                )
                db.add(thread_record)
                db.commit()
                logger.info("Created new thread record")

            # Extract comments with rate limit handling
            all_comments = self.extract_comments_with_retry(
                submission, max_replace_more
            )

            if not all_comments:
                logger.warning("No comments extracted from thread")
                return {
                    "total_comments": 0,
                    "new_comments": 0,
                    "processed_articles": 0,
                    "ticker_links": 0,
                }

            # Get existing comment IDs if skipping existing
            existing_comment_ids = set()
            if skip_existing:
                existing_articles = (
                    db.execute(
                        select(Article.reddit_id).where(
                            Article.source == "reddit_comment"
                        )
                    )
                    .scalars()
                    .all()
                )
                existing_comment_ids = set(existing_articles)

            # Filter new comments
            new_comments = []
            for comment in all_comments:
                if comment.id not in existing_comment_ids:
                    new_comments.append(comment)

            logger.info(
                f"Found {len(new_comments)} new comments out of {len(all_comments)} total"
            )

            if not new_comments:
                logger.info("No new comments to process")
                thread_record.last_scraped_at = datetime.now(UTC)
                thread_record.scraped_comments = len(all_comments)
                thread_record.is_complete = True
                db.commit()
                return {
                    "total_comments": len(all_comments),
                    "new_comments": 0,
                    "processed_articles": 0,
                    "ticker_links": 0,
                }

            # Get tickers for linking
            tickers = db.execute(select(Ticker)).scalars().all()
            linker = TickerLinker(
                tickers, max_scraping_workers=self.max_scraping_workers
            )

            # Process comments with incremental saving
            processed_articles = 0
            total_ticker_links = 0
            processed_count = 0
            batch_count = 0

            logger.info(
                f"Processing {len(new_comments)} comments with incremental saving every {self.batch_save_interval} comments"
            )

            for _i, comment in enumerate(new_comments):
                try:
                    # Parse comment to article
                    article = self.discussion_scraper.parse_comment_to_article(
                        comment, submission
                    )

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

                    # Incremental save every N comments
                    if processed_count % self.batch_save_interval == 0:
                        try:
                            db.commit()
                            batch_count += 1
                            logger.info(
                                f"💾 Saved batch {batch_count}: {processed_count}/{len(new_comments)} comments processed"
                            )

                            # Update thread progress
                            thread_record.scraped_comments = max(
                                thread_record.scraped_comments, processed_count
                            )
                            thread_record.last_scraped_at = datetime.now(UTC)
                            db.commit()

                        except Exception as e:
                            logger.error(f"Error saving batch {batch_count}: {e}")
                            db.rollback()

                    # Log progress every 50 comments
                    if processed_count % 50 == 0:
                        logger.info(
                            f"Processed {processed_count}/{len(new_comments)} comments..."
                        )

                except IntegrityError as e:
                    logger.warning(f"Integrity error for comment {comment.id}: {e}")
                    db.rollback()
                    continue
                except Exception as e:
                    logger.error(f"Error processing comment {comment.id}: {e}")
                    continue

            # Final save
            try:
                db.commit()
                logger.info(f"💾 Final save: {processed_count} comments processed")
            except Exception as e:
                logger.error(f"Error in final save: {e}")
                db.rollback()

            # Update thread record
            thread_record.scraped_comments = len(all_comments)
            thread_record.total_comments = submission.num_comments
            thread_record.last_scraped_at = datetime.now(UTC)
            thread_record.is_complete = True

            db.commit()

            logger.info(
                f"✅ Robust scrape completed: {len(all_comments)} total comments, "
                f"{len(new_comments)} new comments, {processed_articles} articles processed, "
                f"{total_ticker_links} ticker links, {batch_count} batches saved"
            )

            return {
                "total_comments": len(all_comments),
                "new_comments": len(new_comments),
                "processed_articles": processed_articles,
                "ticker_links": total_ticker_links,
                "batches_saved": batch_count,
            }

        except Exception as e:
            logger.error(f"Error in robust thread scraping: {e}")
            db.rollback()
            return {
                "total_comments": 0,
                "new_comments": 0,
                "processed_articles": 0,
                "ticker_links": 0,
            }
        finally:
            db.close()

    def scrape_latest_daily_threads_robust(
        self,
        subreddit_name: str = "wallstreetbets",
        max_threads: int = 1,
        max_replace_more: int | None = None,
    ) -> dict[str, Any]:
        """Scrape latest daily discussion threads with robust error handling.

        Args:
            subreddit_name: Name of the subreddit to scrape
            max_threads: Maximum number of threads to scrape
            max_replace_more: Maximum "more comments" to expand per thread

        Returns:
            Dictionary with scraping results
        """
        if not self.reddit:
            raise RuntimeError("Reddit instance not initialized.")

        logger.info(
            f"Starting robust scraping of latest {max_threads} daily threads from r/{subreddit_name}"
        )

        # Find daily discussion threads
        discussion_threads = self.discussion_scraper.find_daily_discussion_threads(
            subreddit_name, limit=max_threads
        )

        if not discussion_threads:
            logger.warning("No daily discussion threads found")
            return {
                "threads_processed": 0,
                "total_comments": 0,
                "new_comments": 0,
                "articles": 0,
                "ticker_links": 0,
            }

        logger.info(f"Found {len(discussion_threads)} daily discussion threads")

        total_stats = {
            "threads_processed": 0,
            "total_comments": 0,
            "new_comments": 0,
            "articles": 0,
            "ticker_links": 0,
            "batches_saved": 0,
        }

        for i, thread in enumerate(discussion_threads, 1):
            logger.info(
                f"Processing thread {i}/{len(discussion_threads)}: {thread.title}"
            )

            try:
                stats = self.scrape_thread_robust(
                    thread, skip_existing=True, max_replace_more=max_replace_more
                )

                total_stats["threads_processed"] += 1
                total_stats["total_comments"] += stats["total_comments"]
                total_stats["new_comments"] += stats["new_comments"]
                total_stats["articles"] += stats["processed_articles"]
                total_stats["ticker_links"] += stats["ticker_links"]
                total_stats["batches_saved"] += stats.get("batches_saved", 0)

                logger.info(
                    f"✅ Thread {i} completed: {stats['new_comments']} new comments, {stats['processed_articles']} articles"
                )

            except Exception as e:
                logger.error(f"❌ Error processing thread {i}: {e}")
                continue

        logger.info(f"🎉 Robust scraping completed: {total_stats}")
        return total_stats


def main():
    """Main function for robust Reddit scraping."""
    parser = argparse.ArgumentParser(
        description="Robust Reddit thread scraper with rate limit handling"
    )
    parser.add_argument(
        "--max-threads",
        type=int,
        default=1,
        help="Maximum number of daily threads to scrape (default: 1)",
    )
    parser.add_argument(
        "--max-replace-more",
        type=int,
        default=None,
        help="Maximum 'more comments' to expand per thread (default: None = no limit)",
    )
    parser.add_argument(
        "--subreddit",
        type=str,
        default="wallstreetbets",
        help="Subreddit to scrape (default: wallstreetbets)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose logging",
    )

    args = parser.parse_args()

    # Setup logging
    level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )

    try:
        # Get Reddit credentials
        client_id, client_secret, user_agent = get_reddit_credentials()
        logger.info("✅ Reddit credentials found")

        # Initialize robust scraper
        scraper = RedditRobustScraper()
        scraper.initialize_reddit(client_id, client_secret, user_agent)
        logger.info("✅ Robust Reddit scraper initialized")

        # Scrape latest daily threads
        results = scraper.scrape_latest_daily_threads_robust(
            subreddit_name=args.subreddit,
            max_threads=args.max_threads,
            max_replace_more=args.max_replace_more,
        )

        logger.info("🎉 Robust scraping completed successfully:")
        logger.info(f"  Threads processed: {results['threads_processed']}")
        logger.info(f"  Total comments found: {results['total_comments']}")
        logger.info(f"  New comments scraped: {results['new_comments']}")
        logger.info(f"  Articles created: {results['articles']}")
        logger.info(f"  Ticker links: {results['ticker_links']}")
        logger.info(f"  Batches saved: {results['batches_saved']}")

    except Exception as e:
        logger.error(f"❌ Robust scraping failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
