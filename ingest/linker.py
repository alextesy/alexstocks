"""Article-ticker linking using ticker aliases and context analysis."""

import logging
import re
from typing import List

from app.db.models import Article, ArticleTicker, Ticker
from app.models.dto import TickerLinkDTO
from app.services.content_scraper import get_content_scraper
from app.services.context_analyzer import get_context_analyzer

logger = logging.getLogger(__name__)


class TickerLinker:
    """Links articles to tickers using alias matching and context analysis."""

    def __init__(self, tickers: list[Ticker], max_scraping_workers: int = 10):
        """Initialize linker with ticker data.

        Args:
            tickers: List of Ticker models with aliases
            max_scraping_workers: Maximum number of concurrent scraping threads
        """
        self.tickers = tickers
        self.alias_to_ticker: dict[str, str] = {}
        self.content_scraper = get_content_scraper()
        self.content_scraper.max_workers = max_scraping_workers
        self.context_analyzer = get_context_analyzer()
        self._build_alias_map()

    def _build_alias_map(self) -> None:
        """Build mapping from ticker symbols to ticker symbols (no aliases to prevent false positives)."""
        for ticker in self.tickers:
            # Only add the symbol itself (both cases) - no aliases
            self.alias_to_ticker[ticker.symbol.lower()] = ticker.symbol
            self.alias_to_ticker[ticker.symbol.upper()] = ticker.symbol

        logger.info(f"Built ticker symbol map with {len(self.alias_to_ticker)} entries (no aliases)")

    def _extract_text_for_matching(self, article: Article, use_title_only: bool = False) -> str:
        """Extract text from article for ticker matching.

        Args:
            article: Article model instance
            use_title_only: If True, only use title and description, don't scrape

        Returns:
            Combined text for matching
        """
        # Reddit comments: ONLY use the text field (skip title completely)
        if article.source == 'reddit_comment':
            text = (article.text or "").lower()
        # Reddit posts: use title + text
        elif article.source == 'reddit_post':
            text_parts = []
            if article.title:
                text_parts.append(article.title)
            if article.text:
                text_parts.append(article.text)
            text = " ".join(text_parts).lower()
        # GDELT and other sources: use title + text + scraping if needed
        else:
            text_parts = []

            # Add title
            if article.title:
                text_parts.append(article.title)

            # Add text content if available
            if article.text:
                text_parts.append(article.text)
            elif not use_title_only:
                # Try to scrape content if not available and not title-only mode
                scraped_content = self._scrape_article_content(article.url)
                if scraped_content:
                    text_parts.append(scraped_content)

            text = " ".join(text_parts).lower()
        
        # Limit text length for performance (max 1000 chars for non-Reddit sources)
        if len(text) > 1000:
            # Find the end of the 5th sentence or 1000 chars, whichever comes first
            sentences = text.split('.')
            if len(sentences) > 5:
                text = '.'.join(sentences[:5]) + '.'
            else:
                text = text[:1000]
        
        return text
    
    def _fast_reddit_comment_linking(self, article: Article) -> list[TickerLinkDTO]:
        """Ultra-fast linking for Reddit comments - check all tickers but skip context analysis."""
        text = (article.text or "").lower()
        
        if not text:
            return []
        
        # Limit text to first few sentences for performance (max 500 chars)
        if len(text) > 500:
            # Find the end of the 3rd sentence or 500 chars, whichever comes first
            sentences = text.split('.')
            if len(sentences) > 3:
                text = '.'.join(sentences[:3]) + '.'
            else:
                text = text[:500]
        
        ticker_links = []
        text_upper = text.upper()
        
        # Pattern 1: $SYMBOL format (highest confidence)
        import re
        dollar_matches = re.findall(r'\$([A-Z]{1,5}(?:\.\w)?)', text_upper)
        for match in dollar_matches:
            if match in self.alias_to_ticker:
                ticker_symbol = self.alias_to_ticker[match]
                ticker_link = TickerLinkDTO(
                    ticker=ticker_symbol,
                    confidence=0.9,  # High confidence for $SYMBOL
                    matched_terms=[f"${match}"],
                    reasoning=["dollar_symbol_format"]
                )
                ticker_links.append(ticker_link)
        
        # Pattern 2: Check ticker symbols (but be very restrictive)
        # Only match if:
        # 1. Single character tickers: ONLY with $ prefix
        # 2. Common word tickers: ONLY with $ prefix  
        # 3. Other tickers: normal word boundaries
        
        # First, identify common word tickers and single character tickers
        common_words = {'NOW', 'DAY', 'OUT', 'TIME', 'WEEK', 'GOOD', 'ALL', 'ARE', 'NEW', 'OLD', 'ONE', 'TWO', 'FOUR', 'FIVE', 'SIX', 'SEVEN', 'EIGHT', 'NINE', 'TEN', 'BIG', 'SMALL', 'HIGH', 'LOW', 'HOT', 'COLD', 'FAST', 'SLOW', 'HARD', 'SOFT', 'LONG', 'SHORT', 'WIDE', 'NARROW', 'DEEP', 'SHALLOW', 'THICK', 'THIN', 'HEAVY', 'LIGHT', 'STRONG', 'WEAK', 'RICH', 'POOR', 'YOUNG', 'OLD', 'FRESH', 'STALE', 'CLEAN', 'DIRTY', 'DRY', 'WET', 'FULL', 'EMPTY', 'OPEN', 'CLOSED', 'FREE', 'BUSY', 'QUIET', 'LOUD', 'BRIGHT', 'DARK', 'LIGHT', 'HEAVY', 'EASY', 'HARD', 'SIMPLE', 'COMPLEX', 'SAFE', 'DANGEROUS', 'HAPPY', 'SAD', 'GOOD', 'BAD', 'BEST', 'WORST', 'BETTER', 'WORSE', 'BIG', 'SMALL', 'LARGE', 'TINY', 'HUGE', 'MINI', 'MAXI', 'MEGA', 'MICRO', 'MACRO', 'SUPER', 'ULTRA', 'HYPER', 'MULTI', 'UNI', 'BI', 'TRI', 'QUAD', 'PENTA', 'HEXA', 'HEPTA', 'OCTA', 'NONA', 'DECA', 'CENTI', 'MILLI', 'KILO', 'MEGA', 'GIGA', 'TERA', 'PETA', 'EXA', 'ZETTA', 'YOTTA'}
        
        # Find all potential ticker symbols
        symbol_pattern = r'(?<![A-Za-z0-9])([A-Z]{1,5}(?:\.\w)?)(?![A-Za-z0-9])'
        symbol_matches = re.findall(symbol_pattern, text_upper)
        
        for match in symbol_matches:
            if match in self.alias_to_ticker:
                ticker_symbol = self.alias_to_ticker[match]
                
                # Skip if we already found this ticker via $SYMBOL format
                if any(link.ticker == ticker_symbol for link in ticker_links):
                    continue
                
                # Apply strict rules:
                # 1. Single character tickers: ONLY with $ prefix
                if len(match) == 1:
                    continue  # Skip single character tickers without $
                
                # 2. Common word tickers: ONLY with $ prefix
                if match in common_words:
                    continue  # Skip common word tickers without $
                
                # 3. Other tickers: allow normal matching
                ticker_link = TickerLinkDTO(
                    ticker=ticker_symbol,
                    confidence=0.7,  # Medium confidence for symbol match
                    matched_terms=[match],
                    reasoning=["ticker_symbol"]
                )
                ticker_links.append(ticker_link)
        
        return ticker_links
    
    def _scrape_article_content(self, url: str) -> str | None:
        """Scrape article content from URL.
        
        Args:
            url: Article URL to scrape
            
        Returns:
            Scraped content or None if scraping fails
        """
        try:
            if self.content_scraper.is_scrapable_url(url):
                return self.content_scraper.scrape_article_content(url)
        except Exception as e:
            logger.warning(f"Failed to scrape content from {url}: {e}")
        
        return None

    def _find_ticker_matches(self, text: str) -> dict[str, list[str]]:
        """Find ticker matches in text with matched terms.

        Args:
            text: Text to search for ticker mentions

        Returns:
            Dictionary mapping ticker symbols to lists of matched terms
        """
        matches = {}

        # Pattern matching for $SYMBOL format (highest priority)
        dollar_pattern = r"\$([A-Z]{1,5}(?:\.[A-Z])?)"
        dollar_matches = re.findall(dollar_pattern, text.upper())
        for match in dollar_matches:
            if match in self.alias_to_ticker:
                ticker_symbol = self.alias_to_ticker[match]
                if ticker_symbol not in matches:
                    matches[ticker_symbol] = []
                # Find the actual $SYMBOL in the original text
                dollar_symbol = f"${match}"
                if dollar_symbol in text:
                    matches[ticker_symbol].append(dollar_symbol)
                elif dollar_symbol.lower() in text:
                    matches[ticker_symbol].append(dollar_symbol.lower())

        # Pattern matching for SYMBOL format (uppercase, strict word boundaries)
        # Use negative lookbehind/lookahead to prevent substring matches
        symbol_pattern = r"(?<![A-Za-z0-9])([A-Z]{1,5}(?:\.[A-Z])?)(?![A-Za-z0-9])"
        symbol_matches = re.findall(symbol_pattern, text.upper())
        
        # Define common words that should only match with $ prefix
        common_words = {'NOW', 'DAY', 'OUT', 'TIME', 'WEEK', 'GOOD', 'ALL', 'ARE', 'NEW', 'OLD', 'ONE', 'TWO', 'FOUR', 'FIVE', 'SIX', 'SEVEN', 'EIGHT', 'NINE', 'TEN', 'BIG', 'SMALL', 'HIGH', 'LOW', 'HOT', 'COLD', 'FAST', 'SLOW', 'HARD', 'SOFT', 'LONG', 'SHORT', 'WIDE', 'NARROW', 'DEEP', 'SHALLOW', 'THICK', 'THIN', 'HEAVY', 'LIGHT', 'STRONG', 'WEAK', 'RICH', 'POOR', 'YOUNG', 'OLD', 'FRESH', 'STALE', 'CLEAN', 'DIRTY', 'DRY', 'WET', 'FULL', 'EMPTY', 'OPEN', 'CLOSED', 'FREE', 'BUSY', 'QUIET', 'LOUD', 'BRIGHT', 'DARK', 'LIGHT', 'HEAVY', 'EASY', 'HARD', 'SIMPLE', 'COMPLEX', 'SAFE', 'DANGEROUS', 'HAPPY', 'SAD', 'GOOD', 'BAD', 'BEST', 'WORST', 'BETTER', 'WORSE', 'BIG', 'SMALL', 'LARGE', 'TINY', 'HUGE', 'MINI', 'MAXI', 'MEGA', 'MICRO', 'MACRO', 'SUPER', 'ULTRA', 'HYPER', 'MULTI', 'UNI', 'BI', 'TRI', 'QUAD', 'PENTA', 'HEXA', 'HEPTA', 'OCTA', 'NONA', 'DECA', 'CENTI', 'MILLI', 'KILO', 'MEGA', 'GIGA', 'TERA', 'PETA', 'EXA', 'ZETTA', 'YOTTA'}
        
        for match in symbol_matches:
            if match in self.alias_to_ticker:
                ticker_symbol = self.alias_to_ticker[match]
                
                # Apply strict rules:
                # 1. Single character tickers: ONLY with $ prefix
                if len(match) == 1:
                    continue  # Skip single character tickers without $
                
                # 2. Common word tickers: ONLY with $ prefix
                if match in common_words:
                    continue  # Skip common word tickers without $
                
                # 3. Other tickers: allow normal matching
                if ticker_symbol not in matches:
                    matches[ticker_symbol] = []
                # Find the actual symbol in the original text (preserve case)
                if match in text:
                    matches[ticker_symbol].append(match)
                elif match.lower() in text:
                    matches[ticker_symbol].append(match.lower())

        # No company name matching - only ticker symbols to prevent false positives

        # Deduplicate matched terms for each ticker
        for ticker_symbol in matches:
            matches[ticker_symbol] = list(set(matches[ticker_symbol]))

        return matches


    def link_article(self, article: Article, use_title_only: bool = True) -> list[TickerLinkDTO]:
        """Link an article to relevant tickers with context analysis.

        Args:
            article: Article model instance
            use_title_only: If True, only use title/description for matching (faster)

        Returns:
            List of TickerLinkDTO with confidence and reasoning
        """
        # Fast path for Reddit comments - skip complex analysis
        if article.source == 'reddit_comment':
            return self._fast_reddit_comment_linking(article)
        
        # Extract text for matching
        text = self._extract_text_for_matching(article, use_title_only=use_title_only)

        if not text:
            logger.debug(f"No text available for article {article.url}")
            return []

        # Find ticker matches with terms
        ticker_matches = self._find_ticker_matches(text)

        if not ticker_matches:
            logger.debug(f"No ticker matches found for article {article.url}")
            return []

        # Analyze each match with context
        ticker_links = []
        for ticker_symbol, matched_terms in ticker_matches.items():
            # Use context analyzer to determine relevance
            confidence, reasoning = self.context_analyzer.analyze_ticker_relevance(
                ticker_symbol, text, matched_terms
            )
            
            # Only include matches with reasonable confidence
            if confidence >= 0.5:  # Higher minimum confidence threshold
                ticker_link = TickerLinkDTO(
                    ticker=ticker_symbol,
                    confidence=confidence,
                    matched_terms=matched_terms,
                    reasoning=reasoning
                )
                ticker_links.append(ticker_link)

        logger.debug(f"Linked article {article.url} to {len(ticker_links)} tickers")
        return ticker_links
    
    def link_article_to_db(self, article: Article) -> list[ArticleTicker]:
        """Link an article to relevant tickers for database storage.

        Args:
            article: Article model instance

        Returns:
            List of ArticleTicker relationships
        """
        # Get ticker links with context analysis
        ticker_links = self.link_article(article)
        
        # Convert to ArticleTicker objects for database
        article_tickers = []
        for link in ticker_links:
            article_ticker = ArticleTicker(
                ticker=link.ticker,
                confidence=link.confidence,
                matched_terms=link.matched_terms
            )
            article_tickers.append(article_ticker)
        
        return article_tickers

    def _calculate_confidence(self, text: str, ticker_symbol: str) -> float:
        """Calculate confidence score for ticker match.

        Args:
            text: Text where ticker was found
            ticker_symbol: Ticker symbol that was matched

        Returns:
            Confidence score between 0.0 and 1.0
        """
        # Base confidence
        confidence = 0.5

        # Higher confidence for $SYMBOL format
        if f"${ticker_symbol.lower()}" in text:
            confidence = 0.9

        # Higher confidence for exact symbol match
        elif ticker_symbol.lower() in text:
            confidence = 0.8

        # Check for company name mentions
        ticker_obj = next((t for t in self.tickers if t.symbol == ticker_symbol), None)
        if ticker_obj:
            # Higher confidence if company name is mentioned
            company_name_words = ticker_obj.name.lower().split()
            for word in company_name_words:
                if (
                    len(word) > 3 and word in text
                ):  # Only consider words longer than 3 chars
                    confidence = min(confidence + 0.1, 1.0)

        return confidence

    def link_articles(
        self, articles: list[Article]
    ) -> list[tuple[Article, list[TickerLinkDTO]]]:
        """Link multiple articles to tickers with context analysis.

        Args:
            articles: List of Article model instances

        Returns:
            List of tuples (article, ticker_links)
        """
        results = []

        for article in articles:
            ticker_links = self.link_article(article)
            results.append((article, ticker_links))

        # Log summary
        total_links = sum(len(links) for _, links in results)
        linked_articles = sum(1 for _, links in results if links)

        logger.info(
            f"Linked {linked_articles}/{len(articles)} articles to {total_links} ticker relationships"
        )

        return results
    
    def link_articles_with_multithreaded_scraping(
        self, articles: list[Article]
    ) -> list[tuple[Article, list[TickerLinkDTO]]]:
        """Link multiple articles to tickers with smart multithreaded content scraping.

        Args:
            articles: List of Article model instances

        Returns:
            List of tuples (article, ticker_links)
        """
        # First pass: Link articles with existing content to find potential matches
        logger.info(f"First pass: Linking {len(articles)} articles with existing content")
        initial_results = []
        articles_needing_scraping = []
        
        for article in articles:
            # First try with title only (fast)
            ticker_links = self.link_article(article, use_title_only=True)
            initial_results.append((article, ticker_links))
            
            # If no matches found and no text content, mark for scraping
            if not ticker_links and not article.text:
                articles_needing_scraping.append(article)
        
        # Pre-filter articles that need scraping based on title content
        if articles_needing_scraping:
            potential_matches = self._quick_title_filter(articles_needing_scraping)
            logger.info(f"Title filter: {len(potential_matches)}/{len(articles_needing_scraping)} articles have potential matches in title")
            articles_needing_scraping = potential_matches
        
        # Only scrape articles that might have ticker matches but no content
        if articles_needing_scraping:
            logger.info(f"Second pass: Scraping content for {len(articles_needing_scraping)} articles with potential matches")
            urls_to_scrape = [article.url for article in articles_needing_scraping]
            scraped_content = self.content_scraper.scrape_articles_multithreaded(urls_to_scrape)
            
            # Re-link articles with scraped content
            for i, (article, ticker_links) in enumerate(initial_results):
                if article in articles_needing_scraping and article.url in scraped_content and scraped_content[article.url]:
                    # Temporarily set the text content for linking
                    original_text = article.text
                    article.text = scraped_content[article.url]
                    # Use full content (not title-only) for re-linking
                    ticker_links = self.link_article(article, use_title_only=False)
                    article.text = original_text  # Restore original text
                    initial_results[i] = (article, ticker_links)

        # Log summary
        total_links = sum(len(links) for _, links in initial_results)
        linked_articles = sum(1 for _, links in initial_results if links)

        logger.info(
            f"Linked {linked_articles}/{len(articles)} articles to {total_links} ticker relationships"
        )

        return initial_results
    
    def _quick_title_filter(self, articles: list[Article]) -> list[Article]:
        """Quick filter articles based on title content to identify potential matches.
        
        Args:
            articles: List of articles to filter
            
        Returns:
            List of articles that might have ticker matches
        """
        potential_matches = []
        
        for article in articles:
            if not article.title:
                continue
                
            title_lower = article.title.lower()
            
            # Check if title contains any ticker symbols or company names
            for alias, ticker_symbol in self.alias_to_ticker.items():
                if alias in title_lower:
                    potential_matches.append(article)
                    break
        
        return potential_matches
    
    def link_articles_to_db_with_multithreaded_scraping(
        self, articles: list[Article]
    ) -> list[tuple[Article, list[ArticleTicker]]]:
        """Link multiple articles to tickers with multithreaded scraping for database storage.

        Args:
            articles: List of Article model instances

        Returns:
            List of tuples (article, article_tickers)
        """
        # Get ticker links with multithreaded scraping
        ticker_links_results = self.link_articles_with_multithreaded_scraping(articles)
        
        # Convert to ArticleTicker objects for database
        results = []
        for article, ticker_links in ticker_links_results:
            article_tickers = []
            for link in ticker_links:
                article_ticker = ArticleTicker(
                    ticker=link.ticker,
                    confidence=link.confidence
                )
                article_tickers.append(article_ticker)
            
            results.append((article, article_tickers))
        
        return results
    
    def link_articles_to_db(
        self, articles: list[Article]
    ) -> list[tuple[Article, list[ArticleTicker]]]:
        """Link multiple articles to tickers for database storage.

        Args:
            articles: List of Article model instances

        Returns:
            List of tuples (article, article_tickers)
        """
        results = []

        for article in articles:
            article_tickers = self.link_article_to_db(article)
            results.append((article, article_tickers))

        # Log summary
        total_links = sum(len(tickers) for _, tickers in results)
        linked_articles = sum(1 for _, tickers in results if tickers)

        logger.info(
            f"Linked {linked_articles}/{len(articles)} articles to {total_links} ticker relationships"
        )

        return results
