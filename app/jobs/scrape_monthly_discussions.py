#!/usr/bin/env python3
"""Job to scrape the last month of WallStreetBets daily discussions with sentiment analysis."""

import argparse
import logging
import sys
import time
from datetime import UTC, datetime, timedelta
from datetime import date as date_type
from typing import Any

import praw
from dotenv import load_dotenv
from praw.models import Comment, Submission
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import Article, ArticleTicker, RedditThread, Ticker
from app.db.session import SessionLocal
from ingest.linker import TickerLinker
from ingest.reddit_discussion_scraper import (
    RedditDiscussionScraper,
    get_reddit_credentials,
)

# Load environment variables from .env file
load_dotenv()

logger = logging.getLogger(__name__)


class MonthlyDiscussionScraper:
    """Scraper for historical daily discussion threads from the last month."""

    def __init__(self, max_scraping_workers: int = 5):
        """Initialize the monthly scraper.

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

    def find_historical_daily_threads(
        self,
        subreddit_name: str = "wallstreetbets",
        days_back: int = 30,
        max_posts_per_search: int = 200,
    ) -> list[Submission]:
        """Find daily discussion threads from the last N days.

        Args:
            subreddit_name: Name of the subreddit
            days_back: Number of days to look back
            max_posts_per_search: Maximum posts to check per search method

        Returns:
            List of daily discussion thread submissions
        """
        if not self.reddit:
            raise RuntimeError("Reddit instance not initialized.")

        try:
            subreddit = self.reddit.subreddit(subreddit_name)
            all_daily_threads = []

            # Calculate the start date
            end_date = datetime.now(UTC)
            start_date = end_date - timedelta(days=days_back)

            logger.info(
                f"Searching for daily discussions from {start_date.date()} to {end_date.date()}"
            )

            # Define discussion thread keywords
            discussion_keywords = [
                "daily discussion",
                "weekend discussion",
                "moves tomorrow",
                "daily thread",
                "discussion thread",
                "daily chat",
                "weekend chat",
            ]

            # Search through multiple methods to find historical threads
            search_methods = [
                ("hot", "hot posts"),
                ("new", "new posts"),
                ("top_day", "top posts (day)"),
                ("top_week", "top posts (week)"),
                ("top_month", "top posts (month)"),
            ]

            for method, description in search_methods:
                logger.info(f"Searching {description}...")

                try:
                    if method == "hot":
                        posts = list(subreddit.hot(limit=max_posts_per_search))
                    elif method == "new":
                        posts = list(subreddit.new(limit=max_posts_per_search))
                    elif method == "top_day":
                        posts = list(
                            subreddit.top(time_filter="day", limit=max_posts_per_search)
                        )
                    elif method == "top_week":
                        posts = list(
                            subreddit.top(
                                time_filter="week", limit=max_posts_per_search
                            )
                        )
                    elif method == "top_month":
                        posts = list(
                            subreddit.top(
                                time_filter="month", limit=max_posts_per_search
                            )
                        )

                    found_in_method = 0
                    for post in posts:
                        post_date = datetime.fromtimestamp(post.created_utc, tz=UTC)

                        # Check if post is within our date range
                        if start_date <= post_date <= end_date:
                            title_lower = post.title.lower()
                            if any(
                                keyword in title_lower
                                for keyword in discussion_keywords
                            ):
                                # Avoid duplicates
                                if post not in all_daily_threads:
                                    all_daily_threads.append(post)
                                    found_in_method += 1
                                    logger.info(
                                        f"Found daily thread: {post.title} ({post_date.date()})"
                                    )

                    logger.info(f"Found {found_in_method} new threads in {description}")

                except Exception as e:
                    logger.warning(f"Error searching {description}: {e}")
                    continue

            # Sort by creation date (newest first)
            all_daily_threads.sort(key=lambda x: x.created_utc, reverse=True)

            # Log summary by date
            threads_by_date: dict[date_type, list[Any]] = {}
            for thread in all_daily_threads:
                thread_date = datetime.fromtimestamp(thread.created_utc, tz=UTC).date()
                if thread_date not in threads_by_date:
                    threads_by_date[thread_date] = []
                threads_by_date[thread_date].append(thread)

            logger.info(
                f"Found {len(all_daily_threads)} daily discussion threads from the last {days_back} days"
            )
            logger.info("Threads by date:")
            for date in sorted(threads_by_date.keys(), reverse=True):
                threads = threads_by_date[date]
                logger.info(f"  {date}: {len(threads)} threads")
                for thread in threads:
                    logger.info(f"    - {thread.title}")

            return all_daily_threads

        except Exception as e:
            logger.error(f"Error finding historical daily threads: {e}")
            return []

    def extract_all_comments_from_thread(
        self, submission: Submission, max_replace_more: int = 10
    ) -> list[Comment]:
        """Extract ALL comments from a thread including nested replies.

        Args:
            submission: Reddit submission
            max_replace_more: Maximum "more comments" to expand

        Returns:
            List of ALL comments from the thread
        """
        if not self.reddit:
            raise RuntimeError("Reddit instance not initialized.")

        logger.info(f"Extracting comments from thread: {submission.title}")
        logger.info(f"Thread has {submission.num_comments} total comments")

        try:
            start_time = time.time()

            # Expand "more comments" with a reasonable limit
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
            logger.info(
                f"Extracted {len(valid_comments)} valid comments out of {len(all_comments)} total in {elapsed_time:.2f}s"
            )

            return valid_comments

        except Exception as e:
            logger.error(f"Error extracting comments: {e}")
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
                Article.reddit_url.like(f"%{thread_id}%"),
            )
        )
        return {row[0] for row in result if row[0]}

    def scrape_thread_completely(
        self,
        db: Session,
        submission: Submission,
        tickers: list[Ticker],
        max_replace_more: int = 10,
        skip_existing: bool = True,
    ) -> dict[str, Any]:
        """Scrape a thread completely, getting all comments.

        Args:
            db: Database session
            submission: Reddit submission
            tickers: List of tickers for linking
            max_replace_more: Maximum "more comments" to expand
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
                logger.info(
                    f"Found existing thread record with {thread_record.scraped_comments} scraped comments"
                )
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
                logger.info(
                    f"Found {len(existing_comment_ids)} existing comments in database"
                )

            # Extract ALL comments
            all_comments = self.extract_all_comments_from_thread(
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

            # Filter out existing comments if skipping
            new_comments = []
            if skip_existing:
                for comment in all_comments:
                    if comment.id not in existing_comment_ids:
                        new_comments.append(comment)
                logger.info(
                    f"Found {len(new_comments)} new comments to process (skipping {len(all_comments) - len(new_comments)} existing)"
                )
            else:
                new_comments = all_comments
                logger.info(
                    f"Processing all {len(new_comments)} comments (not skipping existing)"
                )

            if not new_comments:
                logger.info("No new comments to process")
                thread_record.last_scraped_at = datetime.now(UTC)
                return {
                    "total_comments": len(all_comments),
                    "new_comments": 0,
                    "processed_articles": 0,
                    "ticker_links": 0,
                }

            # Initialize ticker linker
            linker = TickerLinker(
                tickers, max_scraping_workers=self.max_scraping_workers
            )

            # Process comments in batches for better performance
            batch_size = 50  # Smaller batches for monthly scraping
            processed_articles = 0
            total_ticker_links = 0
            processed_count = 0

            logger.info(
                f"Processing {len(new_comments)} comments in batches of {batch_size}"
            )

            for i in range(0, len(new_comments), batch_size):
                batch = new_comments[i : i + batch_size]
                batch_num = (i // batch_size) + 1
                total_batches = (len(new_comments) + batch_size - 1) // batch_size

                logger.info(
                    f"Processing batch {batch_num}/{total_batches} ({len(batch)} comments)"
                )

                for comment in batch:
                    try:
                        # Parse comment to article
                        article = self.discussion_scraper.parse_comment_to_article(
                            comment, submission
                        )

                        # Check if article already exists (by reddit_id) if not skipping
                        if not skip_existing:
                            existing_article = db.execute(
                                select(Article).where(
                                    Article.reddit_id == article.reddit_id
                                )
                            ).scalar_one_or_none()

                            if existing_article:
                                logger.debug(
                                    f"Comment {comment.id} already exists, skipping"
                                )
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

                        # Log progress every 25 comments
                        if processed_count % 25 == 0:
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

                # Commit batch
                try:
                    db.commit()
                    logger.info(f"Committed batch {batch_num}/{total_batches}")
                except Exception as e:
                    logger.error(f"Error committing batch {batch_num}: {e}")
                    db.rollback()

            # Update thread record
            thread_record.scraped_comments = max(
                thread_record.scraped_comments, len(all_comments)
            )
            thread_record.total_comments = submission.num_comments
            thread_record.last_scraped_at = datetime.now(UTC)
            thread_record.is_complete = (
                True  # Mark as complete since we got all comments
            )

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
            return {
                "total_comments": 0,
                "new_comments": 0,
                "processed_articles": 0,
                "ticker_links": 0,
            }

    def scrape_monthly_discussions(
        self,
        subreddit_name: str = "wallstreetbets",
        days_back: int = 30,
        max_threads: int = 10,
        max_replace_more: int = 10,
        skip_existing: bool = True,
    ) -> dict[str, Any]:
        """Scrape daily discussion threads from the last month.

        Args:
            subreddit_name: Name of the subreddit
            days_back: Number of days to look back
            max_threads: Maximum number of threads to process
            max_replace_more: Maximum "more comments" to expand per thread
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

            # Find historical daily discussion threads
            daily_threads = self.find_historical_daily_threads(
                subreddit_name, days_back=days_back
            )

            if not daily_threads:
                logger.warning(
                    f"No daily discussion threads found in r/{subreddit_name} for the last {days_back} days"
                )
                return {"error": "No daily discussion threads found"}

            # Process threads (limit to most recent ones)
            processed_threads = daily_threads[:max_threads]
            total_stats = {
                "threads_processed": 0,
                "total_comments": 0,
                "total_new_comments": 0,
                "total_articles": 0,
                "total_ticker_links": 0,
            }

            for i, thread in enumerate(processed_threads, 1):
                thread_date = datetime.fromtimestamp(thread.created_utc, tz=UTC)
                logger.info(
                    f"Processing thread {i}/{len(processed_threads)}: {thread.title} ({thread_date.date()})"
                )

                thread_stats = self.scrape_thread_completely(
                    db, thread, list(tickers), max_replace_more, skip_existing
                )

                # Update totals
                total_stats["threads_processed"] += 1
                total_stats["total_comments"] += thread_stats["total_comments"]
                total_stats["total_new_comments"] += thread_stats["new_comments"]
                total_stats["total_articles"] += thread_stats["processed_articles"]
                total_stats["total_ticker_links"] += thread_stats["ticker_links"]

            logger.info(
                f"Monthly scrape complete: {total_stats['threads_processed']} threads, "
                f"{total_stats['total_comments']} total comments, "
                f"{total_stats['total_new_comments']} new comments, "
                f"{total_stats['total_articles']} articles, "
                f"{total_stats['total_ticker_links']} ticker links"
            )

            return total_stats

        except Exception as e:
            logger.error(f"Error in monthly discussion scrape: {e}")
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


def run_monthly_scraping(
    subreddit: str = "wallstreetbets",
    days_back: int = 30,
    max_threads: int = 10,
    max_replace_more: int = 10,
    max_workers: int = 5,
    skip_existing: bool = True,
    verbose: bool = False,
) -> None:
    """Run monthly Reddit discussion scraping.

    Args:
        subreddit: Subreddit to scrape
        days_back: Number of days to look back
        max_threads: Maximum number of threads to process
        max_replace_more: Maximum "more comments" to expand per thread
        max_workers: Maximum number of workers for ticker linking
        skip_existing: Skip comments already in database
        verbose: Enable verbose logging
    """
    setup_logging(verbose)
    logger.info(f"Starting monthly Reddit discussion scraping for r/{subreddit}")
    logger.info(
        f"Looking back {days_back} days, processing up to {max_threads} threads"
    )

    try:
        # Get Reddit credentials
        client_id, client_secret, user_agent = get_reddit_credentials()
    except ValueError as e:
        logger.error(f"Skipping Reddit scraping due to missing credentials: {e}")
        return

    try:
        # Initialize scraper
        scraper = MonthlyDiscussionScraper(max_scraping_workers=max_workers)
        scraper.initialize_reddit(client_id, client_secret, user_agent)

        # Run monthly scrape
        results = scraper.scrape_monthly_discussions(
            subreddit_name=subreddit,
            days_back=days_back,
            max_threads=max_threads,
            max_replace_more=max_replace_more,
            skip_existing=skip_existing,
        )

        if "error" in results:
            logger.error(f"Scraping failed: {results['error']}")
            sys.exit(1)

        # Log results
        logger.info("🎉 Monthly discussion scraping completed successfully:")
        logger.info(f"  Threads processed: {results['threads_processed']}")
        logger.info(f"  Total comments found: {results['total_comments']}")
        logger.info(f"  New comments scraped: {results['total_new_comments']}")
        logger.info(f"  Articles created: {results['total_articles']}")
        logger.info(f"  Ticker links: {results['total_ticker_links']}")

        print("✅ Monthly Reddit discussion scraping completed successfully")

    except Exception as e:
        logger.error(f"Fatal error during monthly scraping: {e}")
        sys.exit(1)


def main() -> None:
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Monthly Reddit discussion scraping CLI"
    )

    parser.add_argument(
        "--subreddit",
        type=str,
        default="wallstreetbets",
        help="Subreddit to scrape (default: wallstreetbets)",
    )
    parser.add_argument(
        "--days-back",
        type=int,
        default=30,
        help="Number of days to look back (default: 30)",
    )
    parser.add_argument(
        "--max-threads",
        type=int,
        default=10,
        help="Maximum number of threads to process (default: 10)",
    )
    parser.add_argument(
        "--max-replace-more",
        type=int,
        default=10,
        help="Maximum 'more comments' to expand per thread (default: 10)",
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

    run_monthly_scraping(
        subreddit=args.subreddit,
        days_back=args.days_back,
        max_threads=args.max_threads,
        max_replace_more=args.max_replace_more,
        max_workers=args.workers,
        skip_existing=not args.include_existing,
        verbose=args.verbose,
    )


if __name__ == "__main__":
    main()
