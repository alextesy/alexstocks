#!/usr/bin/env python3
"""Quick test script for the full Reddit scraper."""

import logging
import sys
from dotenv import load_dotenv

from ingest.reddit import get_reddit_credentials
from ingest.reddit_full_scraper import RedditFullScraper

# Load environment variables
load_dotenv()

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)

logger = logging.getLogger(__name__)


def test_full_scraper():
    """Test the full scraper functionality."""
    try:
        # Get Reddit credentials
        client_id, client_secret, user_agent = get_reddit_credentials()
        logger.info("✅ Reddit credentials found")
    except ValueError as e:
        logger.error(f"❌ Reddit credentials error: {e}")
        return

    try:
        # Initialize scraper
        scraper = RedditFullScraper(max_scraping_workers=2)
        scraper.initialize_reddit(client_id, client_secret, user_agent)
        logger.info("✅ Reddit scraper initialized")

        # Test finding daily discussion threads
        discussion_threads = scraper.discussion_scraper.find_daily_discussion_threads(
            "wallstreetbets", limit=5
        )
        
        if not discussion_threads:
            logger.warning("❌ No discussion threads found")
            return
        
        logger.info(f"✅ Found {len(discussion_threads)} discussion threads")
        
        # Show thread info
        for i, thread in enumerate(discussion_threads[:3], 1):
            logger.info(f"  {i}. {thread.title}")
            logger.info(f"     Comments: {thread.num_comments}, Score: {thread.score}")
        
        # Test extracting comments from first thread (with limit)
        test_thread = discussion_threads[0]
        logger.info(f"\n🔍 Testing comment extraction from: {test_thread.title}")
        
        # Extract with a reasonable limit for testing
        comments = scraper.extract_all_comments_from_thread(test_thread, max_replace_more=2)
        
        logger.info(f"✅ Extracted {len(comments)} comments from thread")
        
        if comments:
            # Show sample comments
            logger.info("\n📝 Sample comments:")
            for i, comment in enumerate(comments[:3], 1):
                preview = comment.body[:100] + "..." if len(comment.body) > 100 else comment.body
                logger.info(f"  {i}. Author: {comment.author}, Score: {comment.score}")
                logger.info(f"     Preview: {preview}")
        
        logger.info("\n🎉 Full scraper test completed successfully!")
        
    except Exception as e:
        logger.error(f"❌ Error testing full scraper: {e}")


if __name__ == "__main__":
    test_full_scraper()

