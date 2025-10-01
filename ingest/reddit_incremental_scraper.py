"""Incremental Reddit discussion scraper for cron jobs."""

import logging
from datetime import UTC, datetime
from typing import Any

import praw
from dotenv import load_dotenv
from praw.models import Comment, Submission
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import Article, ArticleTicker, RedditThread, Ticker
from app.db.session import SessionLocal

# Sentiment analysis is now handled separately
from ingest.linker import TickerLinker
from ingest.reddit_discussion_scraper import RedditDiscussionScraper

# Load environment variables from .env file
load_dotenv()

logger = logging.getLogger(__name__)


class RedditIncrementalScraper:
    """Incremental Reddit scraper that tracks progress and only scrapes new content."""

    def __init__(self, max_scraping_workers: int = 5):
        """Initialize the incremental scraper.

        Args:
            max_scraping_workers: Maximum number of workers for ticker linking
        """
        self.discussion_scraper = RedditDiscussionScraper()
        self.max_scraping_workers = max_scraping_workers
        self.reddit: praw.Reddit | None = None

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

    def get_or_create_thread_record(
        self, db: Session, submission: Submission
    ) -> tuple[RedditThread, bool]:
        """Get existing thread record or create new one.

        Args:
            db: Database session
            submission: Reddit submission

        Returns:
            Tuple of (RedditThread, is_new)
        """
        # Check if thread already exists
        existing_thread = db.execute(
            select(RedditThread).where(RedditThread.reddit_id == submission.id)
        ).scalar_one_or_none()

        if existing_thread:
            return existing_thread, False

        # Determine thread type
        title_lower = submission.title.lower()
        if "daily discussion" in title_lower:
            thread_type = "daily"
        elif "weekend discussion" in title_lower:
            thread_type = "weekend"
        else:
            thread_type = "other"

        # Create new thread record
        new_thread = RedditThread(
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

        db.add(new_thread)
        db.flush()  # Get the ID
        return new_thread, True

    def get_scraped_comment_ids(self, db: Session, thread_id: str) -> set[str]:
        """Get set of already scraped comment IDs for a thread.

        Args:
            db: Database session
            thread_id: Reddit thread ID

        Returns:
            Set of scraped comment IDs
        """
        # Get all articles that are comments from this thread
        # We can identify them by checking if the reddit_url contains the thread ID
        result = db.execute(
            select(Article.reddit_id).where(
                Article.source == "reddit_comment",
                Article.reddit_url.like(f"%{thread_id}%"),
            )
        )
        return {row[0] for row in result if row[0]}

    def extract_new_comments(
        self,
        submission: Submission,
        scraped_comment_ids: set[str],
        max_comments: int = 1000,
    ) -> list[Comment]:
        """Extract only new comments that haven't been scraped yet.

        Args:
            submission: Reddit submission
            scraped_comment_ids: Set of already scraped comment IDs
            max_comments: Maximum number of new comments to extract

        Returns:
            List of new comments
        """
        if not self.reddit:
            raise RuntimeError("Reddit instance not initialized.")

        try:
            # Expand comments with limit for efficiency
            submission.comments.replace_more(limit=5)

            new_comments = []
            comment_count = 0

            # Extract only new comments
            for comment in submission.comments.list():
                if comment_count >= max_comments:
                    break

                # Skip if already scraped
                if comment.id in scraped_comment_ids:
                    continue

                # Skip deleted/removed comments
                if comment.body in ["[deleted]", "[removed]"]:
                    continue

                new_comments.append(comment)
                comment_count += 1

            logger.info(
                f"Found {len(new_comments)} new comments in thread: {submission.title}"
            )
            return new_comments

        except Exception as e:
            logger.error(f"Error extracting new comments: {e}")
            return []

    def scrape_thread_incremental(
        self,
        db: Session,
        submission: Submission,
        tickers: list[Ticker],
        max_new_comments: int = 1000,
    ) -> dict[str, int]:
        """Scrape a thread incrementally, only processing new comments.

        Args:
            db: Database session
            submission: Reddit submission
            max_new_comments: Maximum number of new comments to process
            tickers: List of tickers for linking

        Returns:
            Dictionary with scraping statistics
        """
        try:
            # Get or create thread record
            thread_record, is_new_thread = self.get_or_create_thread_record(
                db, submission
            )

            # Update thread stats
            thread_record.total_comments = submission.num_comments
            thread_record.upvotes = submission.score

            if is_new_thread:
                logger.info(f"New thread detected: {submission.title}")
                # For new threads, we want to scrape more aggressively
                max_new_comments = min(max_new_comments * 2, 2000)
            else:
                logger.info(
                    f"Existing thread: {submission.title} (scraped: {thread_record.scraped_comments})"
                )

            # Get already scraped comment IDs
            scraped_comment_ids = self.get_scraped_comment_ids(db, submission.id)

            # Extract new comments
            new_comments = self.extract_new_comments(
                submission, scraped_comment_ids, max_new_comments
            )

            if not new_comments:
                logger.info(f"No new comments found in thread: {submission.title}")
                thread_record.last_scraped_at = datetime.now(UTC)
                return {"new_comments": 0, "processed_articles": 0, "ticker_links": 0}

            # Initialize ticker linker
            linker = TickerLinker(
                tickers, max_scraping_workers=self.max_scraping_workers
            )

            # Process new comments
            processed_articles = 0
            total_ticker_links = 0

            for comment in new_comments:
                try:
                    # Parse comment to article
                    article = self.discussion_scraper.parse_comment_to_article(
                        comment, submission
                    )

                    # Check if article already exists (by reddit_id)
                    existing_article = db.execute(
                        select(Article).where(Article.reddit_id == article.reddit_id)
                    ).scalar_one_or_none()

                    if existing_article:
                        logger.debug(f"Comment {comment.id} already exists, skipping")
                        continue

                    # Add article to database (without sentiment analysis)
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

                except IntegrityError as e:
                    logger.warning(f"Integrity error for comment {comment.id}: {e}")
                    db.rollback()
                    continue
                except Exception as e:
                    logger.error(f"Error processing comment {comment.id}: {e}")
                    continue

            # Update thread record
            thread_record.scraped_comments += len(new_comments)
            thread_record.last_scraped_at = datetime.now(UTC)

            # Mark as complete if we've scraped most comments
            if thread_record.scraped_comments >= thread_record.total_comments * 0.95:
                thread_record.is_complete = True

            logger.info(
                f"Thread {submission.title}: {len(new_comments)} new comments, "
                f"{processed_articles} articles processed, {total_ticker_links} ticker links"
            )

            return {
                "new_comments": len(new_comments),
                "processed_articles": processed_articles,
                "ticker_links": total_ticker_links,
                "is_new_thread": is_new_thread,
            }

        except Exception as e:
            logger.error(f"Error in incremental scraping: {e}")
            return {"new_comments": 0, "processed_articles": 0, "ticker_links": 0}

    def run_incremental_scrape(
        self,
        subreddit_name: str = "wallstreetbets",
        max_threads: int = 3,
        max_new_comments_per_thread: int = 500,
    ) -> dict[str, Any]:
        """Run incremental scraping for discussion threads.

        Args:
            subreddit_name: Name of the subreddit
            max_threads: Maximum number of threads to process
            max_new_comments_per_thread: Maximum new comments per thread

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

            # Find discussion threads from current posts
            discussion_threads = self.discussion_scraper.find_daily_discussion_threads(
                subreddit_name, limit=20
            )

            # Also get existing threads from database that are not complete
            existing_threads = (
                db.execute(
                    select(RedditThread)
                    .where(
                        RedditThread.subreddit == subreddit_name,
                        not RedditThread.is_complete,
                    )
                    .order_by(RedditThread.created_at.desc())
                    .limit(5)
                )
                .scalars()
                .all()
            )

            # Convert existing threads to submission objects for processing
            existing_submissions = []
            for thread in existing_threads:
                try:
                    # Get the submission by ID
                    submission = self.reddit.submission(id=thread.reddit_id)
                    existing_submissions.append(submission)
                except Exception as e:
                    logger.warning(
                        f"Could not fetch existing thread {thread.reddit_id}: {e}"
                    )

            # Combine new and existing threads, prioritizing new ones
            all_threads = discussion_threads + existing_submissions

            # Remove duplicates based on reddit_id
            seen_ids = set()
            unique_threads = []
            for thread in all_threads:
                if thread.id not in seen_ids:
                    seen_ids.add(thread.id)
                    unique_threads.append(thread)

            if not unique_threads:
                logger.warning(f"No discussion threads found in r/{subreddit_name}")
                return {"error": "No discussion threads found"}

            # Process threads (prioritize newer ones)
            processed_threads = unique_threads[:max_threads]
            total_stats = {
                "threads_processed": 0,
                "new_threads": 0,
                "total_new_comments": 0,
                "total_articles": 0,
                "total_ticker_links": 0,
            }

            for i, thread in enumerate(processed_threads, 1):
                logger.info(
                    f"Processing thread {i}/{len(processed_threads)}: {thread.title}"
                )

                thread_stats = self.scrape_thread_incremental(
                    db, thread, tickers, max_new_comments_per_thread
                )

                # Update totals
                total_stats["threads_processed"] += 1
                if thread_stats.get("is_new_thread", False):
                    total_stats["new_threads"] += 1
                total_stats["total_new_comments"] += thread_stats["new_comments"]
                total_stats["total_articles"] += thread_stats["processed_articles"]
                total_stats["total_ticker_links"] += thread_stats["ticker_links"]

            # Commit all changes
            db.commit()

            logger.info(
                f"Incremental scrape complete: {total_stats['threads_processed']} threads, "
                f"{total_stats['new_threads']} new threads, "
                f"{total_stats['total_new_comments']} new comments, "
                f"{total_stats['total_articles']} articles, "
                f"{total_stats['total_ticker_links']} ticker links"
            )

            return total_stats

        except Exception as e:
            logger.error(f"Error in incremental scrape: {e}")
            db.rollback()
            return {"error": str(e)}
        finally:
            db.close()

    def get_scraping_status(
        self, subreddit_name: str = "wallstreetbets", check_live_counts: bool = True
    ) -> dict[str, Any]:
        """Get current scraping status for a subreddit.

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
                # Get live comment count from Reddit if requested and reddit instance is available
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
                                f"Updated thread {thread.reddit_id} comment count: {thread.total_comments} -> {current_total_comments}"
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
