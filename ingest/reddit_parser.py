"""Reddit post parsing and Article mapping."""

import logging
from datetime import UTC, datetime

import praw
from dotenv import load_dotenv
from praw.models import Submission

from app.db.models import Article

# Load environment variables from .env file
load_dotenv()

logger = logging.getLogger(__name__)


class RedditParser:
    """Parses Reddit posts and maps them to Article models."""

    def __init__(self):
        """Initialize the Reddit parser."""
        self.reddit = None

    def initialize_reddit(self, client_id: str, client_secret: str, user_agent: str) -> None:
        """Initialize Reddit API client.

        Args:
            client_id: Reddit API client ID
            client_secret: Reddit API client secret
            user_agent: User agent string for Reddit API
        """
        self.reddit = praw.Reddit(
            client_id=client_id,
            client_secret=client_secret,
            user_agent=user_agent
        )
        logger.info("Reddit API client initialized")

    def parse_submission(self, submission: Submission, subreddit_name: str) -> Article:
        """Parse a Reddit submission into an Article model.

        Args:
            submission: Reddit submission object
            subreddit_name: Name of the subreddit

        Returns:
            Article model instance
        """
        # Combine title and selftext for content
        content_parts = []
        if submission.title:
            content_parts.append(submission.title)
        if submission.selftext:
            content_parts.append(submission.selftext)

        text_content = "\n\n".join(content_parts) if content_parts else ""

        # Create Reddit URL
        reddit_url = f"https://reddit.com{submission.permalink}"

        # Parse published timestamp
        published_at = datetime.fromtimestamp(submission.created_utc, tz=UTC)

        article = Article(
            source="reddit",
            url=reddit_url,  # Use Reddit URL as the main URL
            published_at=published_at,
            title=submission.title or "",
            text=text_content,
            lang="en",  # Assume English for Reddit posts
            # Reddit-specific fields
            reddit_id=submission.id,
            subreddit=subreddit_name,
            author=submission.author.name if submission.author else None,
            upvotes=submission.score,
            num_comments=submission.num_comments,
            reddit_url=reddit_url,
        )

        logger.debug(f"Parsed Reddit post: {submission.id} from r/{subreddit_name}")
        return article

    def fetch_subreddit_posts(
        self,
        subreddit_name: str,
        limit: int = 100,
        time_filter: str = "day"
    ) -> list[Submission]:
        """Fetch posts from a subreddit.

        Args:
            subreddit_name: Name of the subreddit (without r/)
            limit: Maximum number of posts to fetch
            time_filter: Time filter ('hour', 'day', 'week', 'month', 'year', 'all')

        Returns:
            List of Reddit submission objects
        """
        if not self.reddit:
            raise ValueError("Reddit client not initialized. Call initialize_reddit() first.")

        try:
            subreddit = self.reddit.subreddit(subreddit_name)

            # Get top posts for the specified time period
            posts = list(subreddit.top(time_filter=time_filter, limit=limit))

            logger.info(f"Fetched {len(posts)} posts from r/{subreddit_name}")
            return posts

        except Exception as e:
            logger.error(f"Error fetching posts from r/{subreddit_name}: {e}")
            return []

    def parse_subreddit_posts(
        self,
        subreddit_name: str,
        limit: int = 100,
        time_filter: str = "day"
    ) -> list[Article]:
        """Parse posts from a subreddit into Article models.

        Args:
            subreddit_name: Name of the subreddit (without r/)
            limit: Maximum number of posts to fetch
            time_filter: Time filter ('hour', 'day', 'week', 'month', 'year', 'all')

        Returns:
            List of Article model instances
        """
        posts = self.fetch_subreddit_posts(subreddit_name, limit, time_filter)
        articles = []

        for post in posts:
            try:
                article = self.parse_submission(post, subreddit_name)
                articles.append(article)
            except Exception as e:
                logger.warning(f"Error parsing post {post.id}: {e}")
                continue

        logger.info(f"Parsed {len(articles)} articles from r/{subreddit_name}")
        return articles

    def parse_multiple_subreddits(
        self,
        subreddit_names: list[str],
        limit_per_subreddit: int = 100,
        time_filter: str = "day"
    ) -> list[Article]:
        """Parse posts from multiple subreddits.

        Args:
            subreddit_names: List of subreddit names (without r/)
            limit_per_subreddit: Maximum number of posts per subreddit
            time_filter: Time filter ('hour', 'day', 'week', 'month', 'year', 'all')

        Returns:
            List of Article model instances from all subreddits
        """
        all_articles = []

        for subreddit_name in subreddit_names:
            try:
                articles = self.parse_subreddit_posts(
                    subreddit_name,
                    limit_per_subreddit,
                    time_filter
                )
                all_articles.extend(articles)
            except Exception as e:
                logger.error(f"Error processing r/{subreddit_name}: {e}")
                continue

        logger.info(f"Total articles parsed from {len(subreddit_names)} subreddits: {len(all_articles)}")
        return all_articles


def get_reddit_parser() -> RedditParser:
    """Get a Reddit parser instance.

    Returns:
        RedditParser instance
    """
    return RedditParser()
