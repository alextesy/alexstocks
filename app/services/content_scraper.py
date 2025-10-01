"""Web content scraping service for article text extraction."""

import logging
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# Common selectors for article content
ARTICLE_SELECTORS = [
    'article',
    '[role="main"]',
    '.article-content',
    '.post-content',
    '.entry-content',
    '.content',
    '.story-body',
    '.article-body',
    '.post-body',
    '.entry-body',
    'main',
    '.main-content'
]

# Selectors to exclude
EXCLUDE_SELECTORS = [
    'nav', 'header', 'footer', '.navigation', '.menu',
    '.sidebar', '.advertisement', '.ads', '.social-share',
    '.comments', '.related-articles', '.newsletter'
]


class ContentScraper:
    """Service for scraping article content from URLs."""

    def __init__(self, timeout: int = 10, max_content_length: int = 50000, max_workers: int = 10):
        """Initialize content scraper.

        Args:
            timeout: Request timeout in seconds
            max_content_length: Maximum content length to extract
            max_workers: Maximum number of concurrent threads for scraping
        """
        self.timeout = timeout
        self.max_content_length = max_content_length
        self.max_workers = max_workers
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })

    def scrape_article_content(self, url: str) -> str | None:
        """Scrape article content from URL.

        Args:
            url: Article URL to scrape

        Returns:
            Extracted article content or None if scraping fails
        """
        try:
            # Validate URL
            parsed_url = urlparse(url)
            if not parsed_url.scheme or not parsed_url.netloc:
                logger.warning(f"Invalid URL: {url}")
                return None

            # Make request
            response = self.session.get(url, timeout=self.timeout)
            response.raise_for_status()

            # Parse HTML
            soup = BeautifulSoup(response.content, 'html.parser')

            # Remove unwanted elements
            for selector in EXCLUDE_SELECTORS:
                for element in soup.select(selector):
                    element.decompose()

            # Try to find article content
            content = self._extract_content(soup)

            if content:
                # Clean and truncate content
                content = self._clean_content(content)
                if len(content) > self.max_content_length:
                    content = content[:self.max_content_length] + "..."

                logger.debug(f"Scraped {len(content)} characters from {url}")
                return content
            else:
                logger.warning(f"No content found for {url}")
                return None

        except requests.RequestException as e:
            logger.warning(f"Failed to fetch {url}: {e}")
            return None
        except Exception as e:
            logger.error(f"Error scraping {url}: {e}")
            return None

    def _extract_content(self, soup: BeautifulSoup) -> str | None:
        """Extract article content from parsed HTML.

        Args:
            soup: BeautifulSoup object

        Returns:
            Extracted content or None
        """
        # Try article selectors first
        for selector in ARTICLE_SELECTORS:
            elements = soup.select(selector)
            if elements:
                # Get the largest element (likely main content)
                largest_element = max(elements, key=lambda x: len(x.get_text()))
                content = largest_element.get_text()
                if len(content.strip()) > 100:  # Minimum content length
                    return content

        # Fallback: try to find content by text density
        paragraphs = soup.find_all('p')
        if paragraphs:
            content_parts = []
            for p in paragraphs:
                text = p.get_text().strip()
                if len(text) > 50:  # Skip short paragraphs
                    content_parts.append(text)

            if content_parts:
                return '\n\n'.join(content_parts)

        # Last resort: get all text
        all_text = soup.get_text()
        if len(all_text.strip()) > 200:
            return all_text

        return None

    def _clean_content(self, content: str) -> str:
        """Clean extracted content.

        Args:
            content: Raw content text

        Returns:
            Cleaned content
        """
        # Remove extra whitespace
        content = re.sub(r'\s+', ' ', content)

        # Remove common noise patterns
        noise_patterns = [
            r'Advertisement\s*',
            r'Subscribe\s*to\s*.*?newsletter',
            r'Follow\s*us\s*on\s*social\s*media',
            r'Share\s*this\s*article',
            r'Read\s*more\s*:',
            r'Continue\s*reading',
            r'Click\s*here\s*to\s*read\s*more',
        ]

        for pattern in noise_patterns:
            content = re.sub(pattern, '', content, flags=re.IGNORECASE)

        # Remove URLs
        content = re.sub(r'https?://\S+', '', content)

        # Remove email addresses
        content = re.sub(r'\S+@\S+', '', content)

        # Remove phone numbers
        content = re.sub(r'\b\d{3}[-.]?\d{3}[-.]?\d{4}\b', '', content)

        return content.strip()

    def scrape_articles_multithreaded(self, urls: list[str]) -> dict[str, str]:
        """Scrape multiple articles concurrently.

        Args:
            urls: List of URLs to scrape

        Returns:
            Dictionary mapping URLs to scraped content (or None if failed)
        """
        results = {}

        # Filter scrapable URLs
        scrapable_urls = [url for url in urls if self.is_scrapable_url(url)]

        if not scrapable_urls:
            logger.debug("No scrapable URLs found")
            return results

        logger.debug(f"Scraping {len(scrapable_urls)} URLs with {self.max_workers} workers")

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # Submit all scraping tasks
            future_to_url = {
                executor.submit(self.scrape_article_content, url): url
                for url in scrapable_urls
            }

            # Collect results as they complete
            for future in as_completed(future_to_url):
                url = future_to_url[future]
                try:
                    content = future.result()
                    results[url] = content
                except Exception as e:
                    logger.warning(f"Failed to scrape {url}: {e}")
                    results[url] = None

        successful_scrapes = sum(1 for content in results.values() if content is not None)
        logger.debug(f"Successfully scraped {successful_scrapes}/{len(scrapable_urls)} URLs")

        return results

    def is_scrapable_url(self, url: str) -> bool:
        """Check if URL is likely scrapable.

        Args:
            url: URL to check

        Returns:
            True if URL appears scrapable
        """
        try:
            parsed = urlparse(url)

            # Check scheme
            if parsed.scheme not in ['http', 'https']:
                return False

            # Check for common non-scrapable patterns
            non_scrapable_patterns = [
                r'\.pdf$',
                r'\.docx?$',
                r'\.xlsx?$',
                r'\.pptx?$',
                r'\.zip$',
                r'\.mp4$',
                r'\.mp3$',
                r'\.jpg$',
                r'\.png$',
                r'\.gif$',
                r'youtube\.com/watch',
                r'youtu\.be/',
                r'twitter\.com/',
                r'facebook\.com/',
                r'instagram\.com/',
                r'linkedin\.com/',
            ]

            for pattern in non_scrapable_patterns:
                if re.search(pattern, url, re.IGNORECASE):
                    return False

            return True

        except Exception:
            return False


def get_content_scraper() -> ContentScraper:
    """Get content scraper instance."""
    return ContentScraper()
