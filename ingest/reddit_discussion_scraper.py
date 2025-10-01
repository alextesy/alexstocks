"""Reddit daily discussion thread scraper with comment extraction."""

import logging
from datetime import UTC, datetime

import praw
from dotenv import load_dotenv
from praw.models import Comment, Submission

from app.db.models import Article

# Load environment variables from .env file
load_dotenv()

logger = logging.getLogger(__name__)


class RedditDiscussionScraper:
    """Scrapes Reddit daily discussion threads and their comments."""

    def __init__(self):
        """Initialize RedditDiscussionScraper."""
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
        try:
            self.reddit = praw.Reddit(
                client_id=client_id,
                client_secret=client_secret,
                user_agent=user_agent,
            )
            logger.info("PRAW Reddit instance initialized successfully.")
        except Exception as e:
            logger.error(f"Failed to initialize PRAW: {e}")
            raise

    def find_daily_discussion_threads(
        self, subreddit_name: str = "wallstreetbets", limit: int = 20
    ) -> list[Submission]:
        """Find daily discussion threads in a subreddit.

        Args:
            subreddit_name: Name of the subreddit
            limit: Maximum number of posts to search through

        Returns:
            List of daily discussion thread submissions
        """
        if not self.reddit:
            raise RuntimeError(
                "Reddit instance not initialized. Call initialize_reddit first."
            )

        try:
            subreddit = self.reddit.subreddit(subreddit_name)
            posts = []

            # Get recent posts from both hot and top to find discussion threads
            for submission in subreddit.hot(limit=limit):
                posts.append(submission)

            # Also check top posts
            for submission in subreddit.top("day", limit=limit):
                if submission not in posts:  # Avoid duplicates
                    posts.append(submission)

            # Filter for daily discussion threads
            daily_discussions = []
            for post in posts:
                title_lower = post.title.lower()
                if any(
                    keyword in title_lower
                    for keyword in [
                        "daily discussion",
                        "weekend discussion",
                        "moves tomorrow",
                    ]
                ):
                    daily_discussions.append(post)

            logger.info(
                f"Found {len(daily_discussions)} discussion threads in r/{subreddit_name}"
            )
            return daily_discussions

        except Exception as e:
            logger.error(f"Error finding discussion threads: {e}")
            return []

    def extract_comments_from_thread(
        self, submission: Submission, max_comments: int = 100
    ) -> list[Comment]:
        """Extract comments from a discussion thread.

        Args:
            submission: The discussion thread submission
            max_comments: Maximum number of comments to extract

        Returns:
            List of comments from the thread
        """
        if not self.reddit:
            raise RuntimeError("Reddit instance not initialized.")

        try:
            # Expand comments with limit for testing
            submission.comments.replace_more(
                limit=2
            )  # Limit to 2 "more comments" expansions

            comments = []
            comment_count = 0

            # Extract comments with limit
            for comment in submission.comments.list():
                if comment_count >= max_comments:
                    break

                # Skip deleted/removed comments
                if comment.body in ["[deleted]", "[removed]"]:
                    continue

                comments.append(comment)
                comment_count += 1

            logger.info(
                f"Extracted {len(comments)} comments from thread: {submission.title}"
            )
            return comments

        except Exception as e:
            logger.error(f"Error extracting comments: {e}")
            return []

    def parse_comment_to_article(
        self, comment: Comment, parent_submission: Submission
    ) -> Article:
        """Parse a Reddit comment into an Article object.

        Args:
            comment: The Reddit comment
            parent_submission: The parent discussion thread

        Returns:
            Article object representing the comment
        """
        try:
            # Convert Reddit timestamp to datetime
            published_at = datetime.fromtimestamp(comment.created_utc, tz=UTC)

            # Create a unique URL for the comment
            comment_url = f"https://www.reddit.com{comment.permalink}"

            # Create article from comment
            article = Article(
                source="reddit_comment",
                url=comment_url,
                published_at=published_at,
                title=f"Comment in: {parent_submission.title}",
                text=comment.body,
                lang="en",
                reddit_id=comment.id,
                subreddit=comment.subreddit.display_name,
                author=comment.author.name if comment.author else "[deleted]",
                upvotes=comment.score,
                num_comments=0,  # Comments don't have sub-comments in our model
                reddit_url=comment_url,
            )

            return article

        except Exception as e:
            logger.error(f"Error parsing comment {comment.id}: {e}")
            raise

    def scrape_daily_discussion_comments(
        self,
        subreddit_name: str = "wallstreetbets",
        max_comments_per_thread: int = 1000,
        max_threads: int = 1,
    ) -> list[Article]:
        """Scrape comments from daily discussion threads.

        Args:
            subreddit_name: Name of the subreddit
            max_comments_per_thread: Maximum comments to extract per thread
            max_threads: Maximum number of discussion threads to process

        Returns:
            List of Article objects representing comments
        """
        if not self.reddit:
            raise RuntimeError("Reddit instance not initialized.")

        try:
            # Find discussion threads
            discussion_threads = self.find_daily_discussion_threads(
                subreddit_name, limit=50
            )

            if not discussion_threads:
                logger.warning(f"No discussion threads found in r/{subreddit_name}")
                return []

            # Process threads (limit to most recent ones)
            processed_threads = discussion_threads[:max_threads]
            all_articles = []

            for i, thread in enumerate(processed_threads, 1):
                logger.info(
                    f"Processing thread {i}/{len(processed_threads)}: {thread.title}"
                )

                # Extract comments from thread
                comments = self.extract_comments_from_thread(
                    thread, max_comments_per_thread
                )

                # Convert comments to articles
                thread_articles = []
                for comment in comments:
                    try:
                        article = self.parse_comment_to_article(comment, thread)
                        thread_articles.append(article)
                    except Exception as e:
                        logger.warning(f"Failed to parse comment {comment.id}: {e}")
                        continue

                all_articles.extend(thread_articles)
                logger.info(
                    f"Processed {len(thread_articles)} comments from thread: {thread.title}"
                )

            logger.info(f"Total articles created from comments: {len(all_articles)}")
            return all_articles

        except Exception as e:
            logger.error(f"Error scraping discussion comments: {e}")
            return []

    def get_discussion_thread_info(
        self, subreddit_name: str = "wallstreetbets"
    ) -> list[dict]:
        """Get information about available discussion threads.

        Args:
            subreddit_name: Name of the subreddit

        Returns:
            List of dictionaries with thread information
        """
        if not self.reddit:
            raise RuntimeError("Reddit instance not initialized.")

        try:
            discussion_threads = self.find_daily_discussion_threads(
                subreddit_name, limit=20
            )

            thread_info = []
            for thread in discussion_threads:
                info = {
                    "title": thread.title,
                    "author": thread.author.name if thread.author else "[deleted]",
                    "upvotes": thread.score,
                    "num_comments": thread.num_comments,
                    "created_utc": thread.created_utc,
                    "url": f"https://www.reddit.com{thread.permalink}",
                    "is_daily": "daily discussion" in thread.title.lower(),
                    "is_weekend": "weekend discussion" in thread.title.lower(),
                }
                thread_info.append(info)

            return thread_info

        except Exception as e:
            logger.error(f"Error getting discussion thread info: {e}")
            return []

    def quick_test(self, subreddit_name: str = "wallstreetbets") -> dict:
        """Quick test method for development and debugging.

        Args:
            subreddit_name: Name of the subreddit to test

        Returns:
            Dictionary with test results
        """
        if not self.reddit:
            raise RuntimeError("Reddit instance not initialized.")

        try:
            # Find discussion threads
            threads = self.find_daily_discussion_threads(subreddit_name, limit=10)

            if not threads:
                return {
                    "status": "no_threads",
                    "message": f"No discussion threads found in r/{subreddit_name}",
                }

            # Test with the first thread
            test_thread = threads[0]

            # Extract a small sample of comments
            comments = self.extract_comments_from_thread(test_thread, max_comments=5)

            # Convert to articles
            articles = []
            for comment in comments:
                try:
                    article = self.parse_comment_to_article(comment, test_thread)
                    articles.append(article)
                except Exception as e:
                    logger.warning(f"Failed to parse comment: {e}")

            return {
                "status": "success",
                "thread_title": test_thread.title,
                "thread_comments": test_thread.num_comments,
                "extracted_comments": len(comments),
                "parsed_articles": len(articles),
                "sample_articles": [
                    {
                        "author": article.author,
                        "upvotes": article.upvotes,
                        "text_preview": (
                            article.text[:100] + "..."
                            if article.text and len(article.text) > 100
                            else article.text or ""
                        ),
                    }
                    for article in articles[:3]
                ],
            }

        except Exception as e:
            return {"status": "error", "message": str(e)}
