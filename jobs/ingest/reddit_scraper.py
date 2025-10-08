"""
Production-ready Reddit scraper for WSB daily/weekend discussions.

Supports:
- Historical backfill by date range (inclusive, UTC)
- Incremental runs every 15 min
- Rate-limit aware with exponential backoff
- Idempotent with stateful tracking
- Comprehensive observability
"""

import logging
import random
import re
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import praw
from dotenv import load_dotenv
from praw.exceptions import RedditAPIException
from praw.models import Comment, Submission
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import Article, ArticleTicker, RedditThread, ScrapingStatus, Ticker
from app.db.session import SessionLocal
from jobs.ingest.linker import TickerLinker
from ingest.reddit_discussion_scraper import RedditDiscussionScraper

load_dotenv()

logger = logging.getLogger(__name__)


@dataclass
class ScrapeStats:
    """Statistics for a scraping run."""

    threads_processed: int = 0
    total_comments: int = 0
    new_comments: int = 0
    articles_created: int = 0
    ticker_links: int = 0
    batches_saved: int = 0
    rate_limit_events: int = 0
    duration_ms: int = 0


@dataclass
class RateLimiter:
    """Advanced rate limiter with exponential backoff."""

    requests_per_minute: int = 90  # Stay under 100 QPM limit
    request_times: list[float] | None = None  # Track request times

    def __post_init__(self):
        if self.request_times is None:
            self.request_times = []

    def check_and_wait(self) -> None:
        """Check and enforce rate limits with proactive throttling."""
        current_time = time.time()

        # Remove requests older than 1 minute
        if self.request_times is not None:
            self.request_times = [
                t for t in self.request_times if current_time - t < 60
            ]
        else:
            self.request_times = []

        # If approaching limit, wait
        if len(self.request_times) >= self.requests_per_minute:
            sleep_time = 60 - (current_time - self.request_times[0]) + 1
            if sleep_time > 0:
                logger.info(
                    f"⏱️  Rate limit approaching ({len(self.request_times)}/{self.requests_per_minute} QPM), "
                    f"sleeping for {sleep_time:.1f}s..."
                )
                time.sleep(sleep_time)
                # Clean up after sleep
                current_time = time.time()
                self.request_times = [
                    t for t in self.request_times if current_time - t < 60
                ]

        # Record this request
        self.request_times.append(current_time)

    def handle_rate_limit_error(
        self, error: Exception, attempt: int, max_retries: int = 3
    ) -> tuple[bool, int]:
        """
        Handle rate limit errors with exponential backoff + jitter.

        Returns:
            Tuple of (should_retry, sleep_seconds)
        """
        error_str = str(error).lower()

        # Check for 429 or RATELIMIT
        if "429" not in error_str and "rate limit" not in error_str:
            return False, 0

        if attempt >= max_retries:
            logger.error(f"❌ Rate limit retries exhausted after {attempt} attempts")
            return False, 0

        # Extract wait time from PRAW exception if available
        wait_seconds = None
        if isinstance(error, RedditAPIException):
            for item in error.items:
                if item.error_type == "RATELIMIT":
                    # Try to extract minutes from message like "you are doing that too much. try again in 5 minutes."
                    match = re.search(r"(\d+)\s*minute", item.message, re.IGNORECASE)
                    if match:
                        wait_seconds = int(match.group(1)) * 60

        # Exponential backoff: 30s, 60s, 120s with jitter
        if wait_seconds is None:
            base_sleep = 30 * (2**attempt)  # 30, 60, 120
            jitter = random.uniform(0, 5)  # 0-5 seconds
            wait_seconds = min(base_sleep + jitter, 180)  # Cap at 3 minutes

        logger.warning(
            f"⚠️  Rate limit hit (attempt {attempt + 1}/{max_retries}): {error}"
        )
        logger.info(f"😴 Sleeping for {wait_seconds:.1f}s with exponential backoff...")

        return True, int(wait_seconds)


class RedditScraper:
    """
    Production Reddit scraper for WSB daily/weekend discussions.

    Implements PRD requirements:
    - Backfill by date range
    - Incremental with stateful tracking
    - Advanced rate limiting
    - Comprehensive observability
    - Idempotent operations
    """

    def __init__(
        self,
        max_scraping_workers: int = 5,
        batch_save_interval: int = 200,
        requests_per_minute: int = 90,
    ):
        """
        Initialize the production scraper.

        Args:
            max_scraping_workers: Workers for ticker linking
            batch_save_interval: Save every N comments
            requests_per_minute: QPM limit (default 90 for safety)
        """
        self.discussion_scraper = RedditDiscussionScraper()
        self.max_scraping_workers = max_scraping_workers
        self.batch_save_interval = batch_save_interval
        self.rate_limiter = RateLimiter(requests_per_minute=requests_per_minute)
        self.reddit: praw.Reddit | None = None

    def initialize_reddit(
        self, client_id: str, client_secret: str, user_agent: str
    ) -> None:
        """Initialize PRAW Reddit instance."""
        self.discussion_scraper.initialize_reddit(client_id, client_secret, user_agent)
        self.reddit = self.discussion_scraper.reddit

    def find_threads_by_date(
        self, subreddit_name: str, target_date: datetime
    ) -> list[Submission]:
        """
        Find daily/weekend discussion threads for a specific date.

        Args:
            subreddit_name: Subreddit name
            target_date: Target date (UTC)

        Returns:
            List of submissions matching the date
        """
        if not self.reddit:
            raise RuntimeError("Reddit instance not initialized")

        # Search recent submissions
        all_threads = self.discussion_scraper.find_daily_discussion_threads(
            subreddit_name, limit=100
        )

        # Filter by date
        target_day = target_date.date()
        matching_threads = []

        for thread in all_threads:
            thread_date = datetime.fromtimestamp(thread.created_utc, tz=UTC).date()
            if thread_date == target_day:
                matching_threads.append(thread)
                logger.info(
                    f"📅 Found thread for {target_day}: {thread.title} (created: {thread_date})"
                )

        return matching_threads

    def extract_comments_with_retry(
        self,
        submission: Submission,
        max_replace_more: int | None = None,
        max_retries: int = 3,
    ) -> list[Comment]:
        """
        Extract comments with advanced rate limit handling.

        Args:
            submission: Reddit submission
            max_replace_more: Max "more comments" to expand (None = unlimited)
            max_retries: Max retries on rate limit

        Returns:
            List of valid comments
        """
        if not self.reddit:
            raise RuntimeError("Reddit instance not initialized")

        logger.info(f"📥 Extracting comments from: {submission.title}")
        logger.info(f"   Total comments reported: {submission.num_comments}")

        for attempt in range(max_retries + 1):
            try:
                self.rate_limiter.check_and_wait()
                start_time = time.time()

                # Adaptively set max_replace_more for huge threads
                if max_replace_more is None:
                    # For very large threads, start conservative
                    if submission.num_comments > 5000:
                        adaptive_limit = 32
                        logger.info(
                            f"🔧 Large thread detected ({submission.num_comments} comments), "
                            f"using adaptive limit: {adaptive_limit}"
                        )
                    else:
                        adaptive_limit = None
                        logger.info("📂 Expanding ALL 'more comments' (no limit)...")
                else:
                    adaptive_limit = max_replace_more
                    logger.info(
                        f"📂 Expanding up to {adaptive_limit} 'more comments'..."
                    )

                # Expand comment tree
                if adaptive_limit is None:
                    submission.comments.replace_more(limit=None)
                else:
                    submission.comments.replace_more(limit=adaptive_limit)

                # Get all comments
                all_comments = submission.comments.list()

                # Filter deleted/removed
                valid_comments = [
                    c for c in all_comments if c.body not in ["[deleted]", "[removed]"]
                ]

                elapsed = time.time() - start_time
                logger.info(
                    f"✅ Extracted {len(valid_comments)} valid comments "
                    f"(out of {len(all_comments)} total) in {elapsed:.2f}s"
                )

                return valid_comments

            except Exception as e:
                should_retry, sleep_seconds = self.rate_limiter.handle_rate_limit_error(
                    e, attempt, max_retries
                )

                if should_retry:
                    time.sleep(sleep_seconds)
                    logger.info(
                        f"🔄 Retrying comment extraction (attempt {attempt + 2}/{max_retries + 1})..."
                    )
                    continue
                else:
                    logger.error(
                        f"❌ Failed to extract comments after {attempt + 1} attempts: {e}"
                    )
                    return []

        return []

    def get_existing_comment_ids(self, db: Session, thread_reddit_id: str) -> set[str]:
        """
        Get existing comment IDs for a thread.

        Args:
            db: Database session
            thread_reddit_id: Reddit thread ID

        Returns:
            Set of existing comment IDs
        """
        result = db.execute(
            select(Article.reddit_id).where(
                Article.source == "reddit_comment",
                Article.reddit_url.like(f"%{thread_reddit_id}%"),
            )
        )
        return {row[0] for row in result if row[0]}

    def get_last_seen_timestamp(
        self, db: Session, thread_reddit_id: str
    ) -> datetime | None:
        """
        Get last seen comment timestamp for incremental scraping.

        Args:
            db: Database session
            thread_reddit_id: Reddit thread ID

        Returns:
            Last seen timestamp or None
        """
        result = db.execute(
            select(Article.published_at)
            .where(
                Article.source == "reddit_comment",
                Article.reddit_url.like(f"%{thread_reddit_id}%"),
            )
            .order_by(Article.published_at.desc())
            .limit(1)
        )
        row = result.first()
        return row[0] if row else None

    def scrape_thread(
        self,
        db: Session,
        submission: Submission,
        tickers: list[Ticker],
        skip_existing: bool = True,
        max_replace_more: int | None = None,
        use_last_seen: bool = True,
    ) -> dict[str, int]:
        """
        Scrape a single thread with comprehensive tracking.

        Args:
            db: Database session
            submission: Reddit submission
            tickers: List of tickers for linking
            skip_existing: Skip comments already in DB
            max_replace_more: Max "more comments" expansion
            use_last_seen: Use last_seen timestamp for filtering

        Returns:
            Dictionary with scraping statistics
        """
        try:
            start_time = time.time()

            # Get or create thread record
            thread_record = db.execute(
                select(RedditThread).where(RedditThread.reddit_id == submission.id)
            ).scalar_one_or_none()

            if not thread_record:
                # Determine thread type
                title_lower = submission.title.lower()
                if "daily discussion" in title_lower:
                    thread_type = "daily"
                elif "weekend discussion" in title_lower:
                    thread_type = "weekend"
                else:
                    thread_type = "other"

                thread_record = RedditThread(
                    reddit_id=submission.id,
                    title=submission.title,
                    subreddit=submission.subreddit.display_name,
                    thread_type=thread_type,
                    url=f"https://reddit.com{submission.permalink}",
                    author=submission.author.name if submission.author else None,
                    upvotes=submission.score,
                    total_comments=submission.num_comments,
                    scraped_comments=0,
                    is_complete=False,
                    created_at=datetime.now(UTC),
                )
                db.add(thread_record)
                db.flush()
                logger.info(f"🆕 New thread: {submission.title}")
            else:
                logger.info(
                    f"📝 Existing thread: {submission.title} "
                    f"(scraped: {thread_record.scraped_comments}/{thread_record.total_comments})"
                )

            # Extract comments
            all_comments = self.extract_comments_with_retry(
                submission, max_replace_more
            )

            if not all_comments:
                logger.warning("⚠️  No comments extracted")
                return {
                    "total_comments": 0,
                    "new_comments": 0,
                    "processed_articles": 0,
                    "ticker_links": 0,
                    "batches_saved": 0,
                    "rate_limit_events": 0,
                }

            # Filter new comments
            new_comments = []
            if skip_existing:
                if use_last_seen:
                    last_seen = self.get_last_seen_timestamp(db, submission.id)
                    if last_seen:
                        logger.info(f"🕐 Using last_seen filter: {last_seen}")
                        new_comments = [
                            c
                            for c in all_comments
                            if datetime.fromtimestamp(c.created_utc, tz=UTC) > last_seen
                        ]
                        logger.info(
                            f"   Filtered {len(new_comments)} comments newer than {last_seen}"
                        )
                    else:
                        # No last_seen, fall back to ID-based filtering
                        existing_ids = self.get_existing_comment_ids(db, submission.id)
                        new_comments = [
                            c for c in all_comments if c.id not in existing_ids
                        ]
                else:
                    # ID-based filtering only
                    existing_ids = self.get_existing_comment_ids(db, submission.id)
                    new_comments = [c for c in all_comments if c.id not in existing_ids]
                    logger.info(
                        f"🔍 ID-based filtering: {len(new_comments)} new out of {len(all_comments)}"
                    )
            else:
                new_comments = all_comments

            if not new_comments:
                logger.info("✅ No new comments to process")
                thread_record.last_scraped_at = datetime.now(UTC)
                thread_record.is_complete = True
                db.commit()
                return {
                    "total_comments": len(all_comments),
                    "new_comments": 0,
                    "processed_articles": 0,
                    "ticker_links": 0,
                    "batches_saved": 0,
                    "rate_limit_events": 0,
                }

            # Initialize ticker linker
            linker = TickerLinker(
                tickers, max_scraping_workers=self.max_scraping_workers
            )

            # Process comments with batched saves
            processed_articles = 0
            total_ticker_links = 0
            processed_count = 0
            batch_count = 0

            logger.info(
                f"🔄 Processing {len(new_comments)} new comments "
                f"(batch save every {self.batch_save_interval})..."
            )

            for _i, comment in enumerate(new_comments):
                try:
                    # Parse comment to article
                    article = self.discussion_scraper.parse_comment_to_article(
                        comment, submission
                    )

                    # Add to DB
                    db.add(article)
                    db.flush()  # Get ID

                    # Link tickers
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

                    # Incremental save
                    if processed_count % self.batch_save_interval == 0:
                        try:
                            db.commit()
                            batch_count += 1
                            logger.info(
                                f"💾 Batch {batch_count} saved: "
                                f"{processed_count}/{len(new_comments)} comments processed"
                            )

                            # Update thread progress
                            thread_record.scraped_comments = (
                                thread_record.scraped_comments + processed_count
                            )
                            thread_record.last_scraped_at = datetime.now(UTC)
                            db.commit()

                        except Exception as e:
                            logger.error(f"❌ Error saving batch {batch_count}: {e}")
                            db.rollback()

                    # Progress log every 50 comments
                    if processed_count % 50 == 0:
                        logger.info(
                            f"   ... {processed_count}/{len(new_comments)} comments"
                        )

                except IntegrityError as e:
                    logger.warning(f"⚠️  Integrity error for {comment.id}: {e}")
                    db.rollback()
                    continue
                except Exception as e:
                    logger.error(f"❌ Error processing {comment.id}: {e}")
                    continue

            # Final save
            try:
                db.commit()
                logger.info(f"💾 Final save: {processed_count} comments processed")
            except Exception as e:
                logger.error(f"❌ Error in final save: {e}")
                db.rollback()

            # Update thread record
            thread_record.scraped_comments = len(all_comments)
            thread_record.total_comments = submission.num_comments
            thread_record.last_scraped_at = datetime.now(UTC)
            thread_record.is_complete = True
            db.commit()

            duration_ms = int((time.time() - start_time) * 1000)
            logger.info(
                f"✅ Thread complete: {len(all_comments)} total, {len(new_comments)} new, "
                f"{processed_articles} articles, {total_ticker_links} links, "
                f"{batch_count} batches, {duration_ms}ms"
            )

            return {
                "total_comments": len(all_comments),
                "new_comments": len(new_comments),
                "processed_articles": processed_articles,
                "ticker_links": total_ticker_links,
                "batches_saved": batch_count,
                "rate_limit_events": 0,  # TODO: track this
            }

        except Exception as e:
            logger.error(f"❌ Error scraping thread: {e}")
            db.rollback()
            return {
                "total_comments": 0,
                "new_comments": 0,
                "processed_articles": 0,
                "ticker_links": 0,
                "batches_saved": 0,
                "rate_limit_events": 0,
            }

    def scrape_incremental(
        self,
        subreddit_name: str = "wallstreetbets",
        max_threads: int = 3,
        max_replace_more: int | None = 32,
    ) -> ScrapeStats:
        """
        Run incremental scraping (for 15-min cron).

        Args:
            subreddit_name: Subreddit to scrape
            max_threads: Max threads to process
            max_replace_more: Max "more comments" expansion

        Returns:
            ScrapeStats with results
        """
        if not self.reddit:
            raise RuntimeError("Reddit instance not initialized")

        start_time = time.time()
        stats = ScrapeStats()

        db = SessionLocal()
        try:
            # Load tickers
            tickers = db.execute(select(Ticker)).scalars().all()
            if not tickers:
                logger.error("❌ No tickers found in database")
                return stats

            # Find latest threads
            discussion_threads = self.discussion_scraper.find_daily_discussion_threads(
                subreddit_name, limit=20
            )

            if not discussion_threads:
                logger.warning(f"⚠️  No discussion threads found in r/{subreddit_name}")
                return stats

            # Process threads
            processed_threads = discussion_threads[:max_threads]
            logger.info(
                f"🚀 Starting incremental scrape: {len(processed_threads)} threads from r/{subreddit_name}"
            )

            for i, thread in enumerate(processed_threads, 1):
                logger.info(f"\n📊 Thread {i}/{len(processed_threads)}: {thread.title}")

                thread_stats = self.scrape_thread(
                    db,
                    thread,
                    list(tickers),
                    skip_existing=True,
                    max_replace_more=max_replace_more,
                    use_last_seen=True,
                )

                # Aggregate stats
                stats.threads_processed += 1
                stats.total_comments += thread_stats["total_comments"]
                stats.new_comments += thread_stats["new_comments"]
                stats.articles_created += thread_stats["processed_articles"]
                stats.ticker_links += thread_stats["ticker_links"]
                stats.batches_saved += thread_stats["batches_saved"]
                stats.rate_limit_events += thread_stats["rate_limit_events"]

            stats.duration_ms = int((time.time() - start_time) * 1000)

            # Update scraping status
            scraping_status = db.execute(
                select(ScrapingStatus).where(ScrapingStatus.source == "reddit")
            ).scalar_one_or_none()

            if scraping_status:
                scraping_status.last_scrape_at = datetime.now(UTC)
                scraping_status.items_scraped = stats.new_comments
                scraping_status.status = "success"
                scraping_status.error_message = None
                scraping_status.updated_at = datetime.now(UTC)
            else:
                scraping_status = ScrapingStatus(
                    source="reddit",
                    last_scrape_at=datetime.now(UTC),
                    items_scraped=stats.new_comments,
                    status="success",
                    error_message=None,
                    updated_at=datetime.now(UTC),
                )
                db.add(scraping_status)

            db.commit()

            logger.info("\n🎉 Incremental scrape complete:")
            logger.info(f"   Threads: {stats.threads_processed}")
            logger.info(
                f"   Comments: {stats.new_comments} new / {stats.total_comments} total"
            )
            logger.info(f"   Articles: {stats.articles_created}")
            logger.info(f"   Ticker links: {stats.ticker_links}")
            logger.info(f"   Duration: {stats.duration_ms}ms")

            return stats

        except Exception as e:
            logger.error(f"❌ Error in incremental scrape: {e}")
            db.rollback()

            # Update scraping status to error
            try:
                scraping_status = db.execute(
                    select(ScrapingStatus).where(ScrapingStatus.source == "reddit")
                ).scalar_one_or_none()

                if scraping_status:
                    scraping_status.status = "error"
                    scraping_status.error_message = str(e)
                    scraping_status.updated_at = datetime.now(UTC)
                else:
                    scraping_status = ScrapingStatus(
                        source="reddit",
                        last_scrape_at=datetime.now(UTC),
                        items_scraped=0,
                        status="error",
                        error_message=str(e),
                        updated_at=datetime.now(UTC),
                    )
                    db.add(scraping_status)
                db.commit()
            except Exception as status_error:
                logger.error(f"Failed to update scraping status: {status_error}")

            return stats
        finally:
            db.close()

    def scrape_backfill(
        self,
        subreddit_name: str,
        start_date: datetime,
        end_date: datetime,
        max_replace_more: int | None = 32,
    ) -> ScrapeStats:
        """
        Run backfill for date range (inclusive).

        Args:
            subreddit_name: Subreddit to scrape
            start_date: Start date (UTC, inclusive)
            end_date: End date (UTC, inclusive)
            max_replace_more: Max "more comments" expansion

        Returns:
            ScrapeStats with results
        """
        if not self.reddit:
            raise RuntimeError("Reddit instance not initialized")

        logger.info(
            f"🗓️  Starting backfill for r/{subreddit_name}: "
            f"{start_date.date()} to {end_date.date()}"
        )

        start_time = time.time()
        stats = ScrapeStats()

        db = SessionLocal()
        try:
            # Load tickers
            tickers = db.execute(select(Ticker)).scalars().all()
            if not tickers:
                logger.error("❌ No tickers found in database")
                return stats

            # Iterate through date range
            current_date = start_date
            while current_date <= end_date:
                logger.info(f"\n📅 Processing date: {current_date.date()}")

                # Find threads for this date
                threads_for_date = self.find_threads_by_date(
                    subreddit_name, current_date
                )

                if not threads_for_date:
                    logger.info(f"   No threads found for {current_date.date()}")
                else:
                    for thread in threads_for_date:
                        logger.info(f"   📊 Scraping: {thread.title}")

                        thread_stats = self.scrape_thread(
                            db,
                            thread,
                            list(tickers),
                            skip_existing=True,
                            max_replace_more=max_replace_more,
                            use_last_seen=False,  # For backfill, use ID-based
                        )

                        # Aggregate
                        stats.threads_processed += 1
                        stats.total_comments += thread_stats["total_comments"]
                        stats.new_comments += thread_stats["new_comments"]
                        stats.articles_created += thread_stats["processed_articles"]
                        stats.ticker_links += thread_stats["ticker_links"]
                        stats.batches_saved += thread_stats["batches_saved"]
                        stats.rate_limit_events += thread_stats["rate_limit_events"]

                # Move to next day
                current_date += timedelta(days=1)

            stats.duration_ms = int((time.time() - start_time) * 1000)

            # Update scraping status
            scraping_status = db.execute(
                select(ScrapingStatus).where(ScrapingStatus.source == "reddit")
            ).scalar_one_or_none()

            if scraping_status:
                scraping_status.last_scrape_at = datetime.now(UTC)
                scraping_status.items_scraped = stats.new_comments
                scraping_status.status = "success"
                scraping_status.error_message = None
                scraping_status.updated_at = datetime.now(UTC)
            else:
                scraping_status = ScrapingStatus(
                    source="reddit",
                    last_scrape_at=datetime.now(UTC),
                    items_scraped=stats.new_comments,
                    status="success",
                    error_message=None,
                    updated_at=datetime.now(UTC),
                )
                db.add(scraping_status)

            db.commit()

            logger.info("\n🎉 Backfill complete:")
            logger.info(f"   Date range: {start_date.date()} to {end_date.date()}")
            logger.info(f"   Threads: {stats.threads_processed}")
            logger.info(
                f"   Comments: {stats.new_comments} new / {stats.total_comments} total"
            )
            logger.info(f"   Articles: {stats.articles_created}")
            logger.info(f"   Ticker links: {stats.ticker_links}")
            logger.info(f"   Duration: {stats.duration_ms}ms")

            return stats

        except Exception as e:
            logger.error(f"❌ Error in backfill: {e}")
            db.rollback()
            return stats
        finally:
            db.close()

    def get_scraping_status(
        self, subreddit_name: str = "wallstreetbets", check_live_counts: bool = True
    ) -> dict[str, Any]:
        """
        Get current scraping status for a subreddit.

        Args:
            subreddit_name: Name of the subreddit
            check_live_counts: Whether to fetch current comment counts from Reddit API

        Returns:
            Dictionary with scraping status
        """
        db = SessionLocal()
        try:
            # Get thread records
            threads = (
                db.execute(
                    select(RedditThread)
                    .where(RedditThread.subreddit == subreddit_name)
                    .order_by(RedditThread.created_at.desc())
                    .limit(10)
                )
                .scalars()
                .all()
            )

            # Get comment count
            comment_count = (
                db.execute(
                    select(Article).where(
                        Article.subreddit == subreddit_name,
                        Article.source == "reddit_comment",
                    )
                )
                .scalars()
                .all()
            )

            recent_threads_data = []
            for thread in threads:
                # Get live comment count from Reddit if requested
                current_total_comments = thread.total_comments
                live_count_error = None

                if check_live_counts and self.reddit:
                    try:
                        submission = self.reddit.submission(id=thread.reddit_id)
                        current_total_comments = submission.num_comments

                        # Update the database record if the count has changed
                        if current_total_comments != thread.total_comments:
                            thread.total_comments = current_total_comments
                            db.commit()
                            logger.info(
                                f"Updated thread {thread.reddit_id} comment count: "
                                f"{thread.total_comments} -> {current_total_comments}"
                            )

                    except Exception as e:
                        logger.warning(
                            f"Failed to get live comment count for thread {thread.reddit_id}: {e}"
                        )
                        live_count_error = str(e)

                thread_data = {
                    "title": thread.title,
                    "type": thread.thread_type,
                    "total_comments": current_total_comments,
                    "scraped_comments": thread.scraped_comments,
                    "completion_rate": (
                        f"{(thread.scraped_comments / current_total_comments * 100):.1f}%"
                        if current_total_comments > 0
                        else "0%"
                    ),
                    "last_scraped": (
                        thread.last_scraped_at.isoformat()
                        if thread.last_scraped_at
                        else None
                    ),
                    "is_complete": thread.is_complete,
                }

                # Add debug info if live count was checked
                if check_live_counts:
                    thread_data["live_count_checked"] = True
                    if live_count_error:
                        thread_data["live_count_error"] = live_count_error
                    elif current_total_comments != thread.total_comments:
                        thread_data["count_updated"] = True

                recent_threads_data.append(thread_data)

            return {
                "subreddit": subreddit_name,
                "total_threads": len(threads),
                "total_comments_scraped": len(comment_count),
                "live_counts_enabled": check_live_counts and self.reddit is not None,
                "recent_threads": recent_threads_data,
            }

        except Exception as e:
            logger.error(f"Error getting scraping status: {e}")
            return {"error": str(e)}
        finally:
            db.close()
