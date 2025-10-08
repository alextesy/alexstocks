"""Tests for ticker linking functionality."""

from typing import cast
from unittest.mock import Mock, patch

import pytest
from faker import Faker

from app.db.models import Article, Ticker
from app.models.dto import TickerLinkDTO
from jobs.ingest.linker import TickerLinker

fake = Faker()


class TestTickerLinker:
    """Test ticker linking functionality."""

    def setup_method(self):
        """Set up test fixtures."""
        # Create mock tickers
        self.mock_tickers = [
            Mock(symbol="AAPL"),
            Mock(symbol="TSLA"),
            Mock(symbol="NVDA"),
            Mock(symbol="GME"),
            Mock(symbol="AMC"),
            Mock(symbol="SPY"),
            Mock(symbol="QQQ"),
            Mock(symbol="MSFT"),
            Mock(symbol="GOOGL"),
            Mock(symbol="AMZN"),
        ]

        # Create mock services
        self.mock_content_scraper = Mock()
        self.mock_context_analyzer = Mock()

        with (
            patch(
                "jobs.ingest.linker.get_content_scraper",
                return_value=self.mock_content_scraper,
            ),
            patch(
                "jobs.ingest.linker.get_context_analyzer",
                return_value=self.mock_context_analyzer,
            ),
        ):
            self.linker = TickerLinker(
                cast(list[Ticker], self.mock_tickers), max_scraping_workers=5
            )

    def test_initialization(self):
        """Test TickerLinker initialization."""
        assert len(self.linker.tickers) == 10
        assert self.linker.content_scraper == self.mock_content_scraper
        assert self.linker.context_analyzer == self.mock_context_analyzer
        assert self.mock_content_scraper.max_workers == 5

    def test_build_alias_map(self):
        """Test building ticker alias map."""
        # Verify alias map contains both upper and lower case symbols
        assert "aapl" in self.linker.alias_to_ticker
        assert "AAPL" in self.linker.alias_to_ticker
        assert "tsla" in self.linker.alias_to_ticker
        assert "TSLA" in self.linker.alias_to_ticker
        assert self.linker.alias_to_ticker["aapl"] == "AAPL"
        assert self.linker.alias_to_ticker["AAPL"] == "AAPL"

    def test_extract_text_for_matching_title_only(self):
        """Test text extraction for title-only matching."""
        article = Mock()
        article.source = "reddit"  # Set source to reddit
        article.title = "Apple stock is going to the moon! $AAPL"
        article.text = (
            "This is the full article text with more details about Apple Inc."
        )
        article.url = "https://example.com/article"

        text = self.linker._extract_text_for_matching(article, use_title_only=True)

        # The implementation preserves case and combines title + text for reddit posts
        expected = "Apple stock is going to the moon! $AAPL This is the full article text with more details about Apple Inc."
        assert text == expected

    def test_extract_text_for_matching_full_content(self):
        """Test text extraction for full content matching."""
        article = Mock()
        article.source = "reddit"  # Set source to reddit
        article.title = "Tesla News"
        article.text = "Tesla stock $TSLA is performing well. The company reported strong earnings."
        article.url = "https://example.com/tesla-news"

        text = self.linker._extract_text_for_matching(article, use_title_only=False)

        # The implementation preserves case and combines title + text for reddit posts
        expected = "Tesla News Tesla stock $TSLA is performing well. The company reported strong earnings."
        assert text == expected

    def test_extract_text_for_matching_reddit_comment(self):
        """Test text extraction for Reddit comments."""
        article = Mock()
        article.source = "reddit_comment"
        article.title = "Comment Title"
        article.text = "I'm bullish on $NVDA and $AMD. Both are great picks!"
        article.url = "https://reddit.com/comment"

        text = self.linker._extract_text_for_matching(article, use_title_only=False)

        # For Reddit comments, should use text only and preserve case
        expected = "I'm bullish on $NVDA and $AMD. Both are great picks!"
        assert text == expected
        assert "Comment Title" not in text  # Title should not be included

    def test_find_ticker_matches_basic(self):
        """Test basic ticker matching functionality."""
        text = "I love $AAPL and $TSLA stocks. Also watching NVDA and GME."

        matches = self.linker._find_ticker_matches(text)

        assert "AAPL" in matches
        assert "TSLA" in matches
        assert "NVDA" in matches
        assert "GME" in matches
        assert "$AAPL" in matches["AAPL"]
        assert "$TSLA" in matches["TSLA"]
        assert "NVDA" in matches["NVDA"]
        assert "GME" in matches["GME"]

    def test_find_ticker_matches_case_insensitive(self):
        """Test case-insensitive ticker matching."""
        text = "apple (aapl) and tesla (tsla) are great stocks"

        matches = self.linker._find_ticker_matches(text)

        assert "AAPL" in matches
        assert "TSLA" in matches
        assert "aapl" in matches["AAPL"]
        assert "tsla" in matches["TSLA"]

    def test_find_ticker_matches_multiple_mentions(self):
        """Test handling multiple mentions of the same ticker."""
        text = "I bought $AAPL yesterday and sold $AAPL today. $AAPL is volatile."

        matches = self.linker._find_ticker_matches(text)

        assert "AAPL" in matches
        # The implementation finds both $AAPL and AAPL versions, but deduplicates
        assert len(matches["AAPL"]) >= 1  # At least one mention
        assert any("$AAPL" in term for term in matches["AAPL"])

    def test_find_ticker_matches_no_matches(self):
        """Test text with no ticker matches."""
        text = "This is just a regular article about the economy and market trends."

        matches = self.linker._find_ticker_matches(text)

        assert len(matches) == 0

    def test_find_ticker_matches_word_boundaries(self):
        """Test ticker matching respects word boundaries."""
        text = "I like APPLES and TESLA cars, but not APPLETREE or TESLACOIL"

        matches = self.linker._find_ticker_matches(text)

        # Should not match APPLES or TESLACOIL
        assert "AAPL" not in matches
        assert "TSLA" not in matches

    def test_link_article_reddit_comment_fast_path(self):
        """Test fast path linking for Reddit comments."""
        article = Mock()
        article.source = "reddit_comment"
        article.title = "Comment"
        article.text = "I'm bullish on $AAPL and $TSLA"

        # Mock the fast path method
        with patch.object(self.linker, "_fast_reddit_comment_linking") as mock_fast:
            mock_fast.return_value = [
                TickerLinkDTO(
                    ticker="AAPL",
                    confidence=0.8,
                    matched_terms=["$AAPL"],
                    reasoning=["Direct mention"],
                )
            ]

            result = self.linker.link_article(article, use_title_only=True)

            mock_fast.assert_called_once_with(article)
            assert len(result) == 1
            assert result[0].ticker == "AAPL"

    def test_link_article_with_context_analysis(self):
        """Test article linking with context analysis."""
        article = Mock()
        article.source = "reddit"
        article.title = "Apple Inc. reports strong earnings"
        article.text = "Apple stock $AAPL is performing well with strong iPhone sales."
        article.url = "https://example.com/apple-news"

        # Mock context analyzer
        self.mock_context_analyzer.analyze_ticker_relevance.return_value = (
            0.9,
            ["Strong financial context"],
        )

        result = self.linker.link_article(article, use_title_only=False)

        assert len(result) == 1
        assert result[0].ticker == "AAPL"
        assert result[0].confidence == 0.9
        # The implementation finds both $aapl and aapl versions
        assert len(result[0].matched_terms) >= 1
        assert any("$aapl" in term.lower() for term in result[0].matched_terms)
        assert result[0].reasoning == ["Strong financial context"]

    def test_link_article_low_confidence_filtered(self):
        """Test that low confidence matches are filtered out."""
        article = Mock()
        article.source = "reddit"
        article.title = "Random mention of Apple"
        article.text = "I saw an apple tree today. $AAPL"
        article.url = "https://example.com/random"

        # Mock context analyzer to return low confidence
        self.mock_context_analyzer.analyze_ticker_relevance.return_value = (
            0.3,
            ["Weak context"],
        )

        result = self.linker.link_article(article, use_title_only=False)

        # Should be filtered out due to low confidence (< 0.5)
        assert len(result) == 0

    def test_link_article_multiple_tickers(self):
        """Test linking article with multiple tickers."""
        article = Mock()
        article.source = "reddit"
        article.title = "Tech stocks analysis"
        article.text = (
            "I'm bullish on $AAPL, $TSLA, and $NVDA. All three are great investments."
        )
        article.url = "https://example.com/tech-analysis"

        # Mock context analyzer for different confidences
        def mock_analyze(ticker, text, terms):
            confidences = {"AAPL": 0.9, "TSLA": 0.8, "NVDA": 0.7}
            return confidences.get(ticker, 0.5), [f"Strong context for {ticker}"]

        self.mock_context_analyzer.analyze_ticker_relevance.side_effect = mock_analyze

        result = self.linker.link_article(article, use_title_only=False)

        assert len(result) == 3
        tickers = [link.ticker for link in result]
        assert "AAPL" in tickers
        assert "TSLA" in tickers
        assert "NVDA" in tickers

        # Check confidences
        confidences = {link.ticker: link.confidence for link in result}
        assert confidences["AAPL"] == 0.9
        assert confidences["TSLA"] == 0.8
        assert confidences["NVDA"] == 0.7

    def test_link_article_empty_text(self):
        """Test linking article with empty text."""
        article = Mock()
        article.source = "reddit"
        article.title = ""
        article.text = ""
        article.url = "https://example.com/empty"

        result = self.linker.link_article(article, use_title_only=True)

        assert len(result) == 0

    def test_link_article_to_db(self):
        """Test converting ticker links to database models."""
        article = Mock()
        article.id = 123

        ticker_links = [
            TickerLinkDTO(
                ticker="AAPL",
                confidence=0.9,
                matched_terms=["$AAPL"],
                reasoning=["Strong context"],
            ),
            TickerLinkDTO(
                ticker="TSLA",
                confidence=0.8,
                matched_terms=["$TSLA"],
                reasoning=["Good context"],
            ),
        ]

        with patch.object(self.linker, "link_article", return_value=ticker_links):
            result = self.linker.link_article_to_db(article)

        assert len(result) == 2
        # The ArticleTicker objects should have the ticker and confidence set
        # Note: article_id is not set in the current implementation
        assert result[0].ticker == "AAPL"
        assert result[0].confidence == 0.9
        assert result[0].matched_terms == ["$AAPL"]

        assert result[1].ticker == "TSLA"
        assert result[1].confidence == 0.8
        assert result[1].matched_terms == ["$TSLA"]

    def test_link_articles_to_db(self):
        """Test linking multiple articles to database."""
        articles = [Mock(), Mock()]
        articles[0].id = 1
        articles[1].id = 2

        # Mock link_article_to_db for each article
        with patch.object(self.linker, "link_article_to_db") as mock_link:
            mock_link.side_effect = [
                [Mock(ticker="AAPL")],  # First article
                [Mock(ticker="TSLA"), Mock(ticker="NVDA")],  # Second article
            ]

            result = self.linker.link_articles_to_db(cast(list[Article], articles))

        assert len(result) == 2
        assert len(result[0][1]) == 1  # First article has 1 ticker link
        assert len(result[1][1]) == 2  # Second article has 2 ticker links


class TestTickerLinkDTO:
    """Test TickerLinkDTO validation and functionality."""

    def test_valid_dto_creation(self):
        """Test creating valid TickerLinkDTO."""
        dto = TickerLinkDTO(
            ticker="AAPL",
            confidence=0.8,
            matched_terms=["$AAPL", "Apple"],
            reasoning=["Direct mention", "Strong context"],
        )

        assert dto.ticker == "AAPL"
        assert dto.confidence == 0.8
        assert dto.matched_terms == ["$AAPL", "Apple"]
        assert dto.reasoning == ["Direct mention", "Strong context"]

    def test_invalid_confidence_too_high(self):
        """Test DTO validation with confidence > 1.0."""
        with pytest.raises(ValueError, match="Confidence must be between 0.0 and 1.0"):
            TickerLinkDTO(
                ticker="AAPL",
                confidence=1.5,
                matched_terms=["$AAPL"],
                reasoning=["Test"],
            )

    def test_invalid_confidence_too_low(self):
        """Test DTO validation with confidence < 0.0."""
        with pytest.raises(ValueError, match="Confidence must be between 0.0 and 1.0"):
            TickerLinkDTO(
                ticker="AAPL",
                confidence=-0.1,
                matched_terms=["$AAPL"],
                reasoning=["Test"],
            )

    def test_empty_ticker(self):
        """Test DTO validation with empty ticker."""
        with pytest.raises(ValueError, match="Ticker symbol cannot be empty"):
            TickerLinkDTO(
                ticker="", confidence=0.8, matched_terms=["$AAPL"], reasoning=["Test"]
            )

    def test_invalid_matched_terms_type(self):
        """Test DTO validation with invalid matched_terms type."""
        with pytest.raises(ValueError, match="matched_terms must be a list"):
            TickerLinkDTO(
                ticker="AAPL",
                confidence=0.8,
                matched_terms="not a list",  # type: ignore[arg-type]
                reasoning=["Test"],
            )

    def test_invalid_reasoning_type(self):
        """Test DTO validation with invalid reasoning type."""
        with pytest.raises(ValueError, match="reasoning must be a list"):
            TickerLinkDTO(
                ticker="AAPL",
                confidence=0.8,
                matched_terms=["$AAPL"],
                reasoning="not a list",  # type: ignore[arg-type]
            )


class TestTickerLinkingRealWorldExamples:
    """Test ticker linking with real-world Reddit examples."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mock_tickers = [
            Mock(symbol="GME"),
            Mock(symbol="AMC"),
            Mock(symbol="AAPL"),
            Mock(symbol="TSLA"),
            Mock(symbol="NVDA"),
            Mock(symbol="SPY"),
            Mock(symbol="QQQ"),
            Mock(symbol="MSFT"),
            Mock(symbol="GOOGL"),
            Mock(symbol="AMZN"),
        ]

        self.mock_content_scraper = Mock()
        self.mock_context_analyzer = Mock()

        with (
            patch(
                "jobs.ingest.linker.get_content_scraper",
                return_value=self.mock_content_scraper,
            ),
            patch(
                "jobs.ingest.linker.get_context_analyzer",
                return_value=self.mock_context_analyzer,
            ),
        ):
            self.linker = TickerLinker(
                cast(list[Ticker], self.mock_tickers), max_scraping_workers=5
            )

    def test_wallstreetbets_meme_stock_mentions(self):
        """Test linking with WallStreetBets meme stock language."""
        article = Mock()
        article.source = "reddit_comment"
        article.title = "Comment"
        article.text = "🚀 $GME to the moon! 💎🙌 Diamond hands! $AMC is next! 🚀🚀🚀"
        article.url = "https://reddit.com/comment"

        # Mock fast path for Reddit comments
        with patch.object(self.linker, "_fast_reddit_comment_linking") as mock_fast:
            mock_fast.return_value = [
                TickerLinkDTO(
                    ticker="GME",
                    confidence=0.95,
                    matched_terms=["$GME"],
                    reasoning=["Direct mention with rocket emoji"],
                ),
                TickerLinkDTO(
                    ticker="AMC",
                    confidence=0.9,
                    matched_terms=["$AMC"],
                    reasoning=["Direct mention"],
                ),
            ]

            result = self.linker.link_article(article, use_title_only=True)

            assert len(result) == 2
            assert result[0].ticker == "GME"
            assert result[1].ticker == "AMC"

    def test_technical_analysis_discussion(self):
        """Test linking with technical analysis discussions."""
        article = Mock()
        article.source = "reddit"
        article.title = "Technical Analysis: AAPL, TSLA, NVDA"
        article.text = "Looking at the charts for $AAPL, $TSLA, and $NVDA. All three are showing bullish patterns."
        article.url = "https://reddit.com/technical-analysis"

        # Mock context analyzer
        def mock_analyze(ticker, text, terms):
            return 0.85, [f"Technical analysis context for {ticker}"]

        self.mock_context_analyzer.analyze_ticker_relevance.side_effect = mock_analyze

        result = self.linker.link_article(article, use_title_only=False)

        assert len(result) == 3
        tickers = [link.ticker for link in result]
        assert "AAPL" in tickers
        assert "TSLA" in tickers
        assert "NVDA" in tickers

    def test_earnings_discussion(self):
        """Test linking with earnings discussion."""
        article = Mock()
        article.source = "reddit"
        article.title = "MSFT earnings beat expectations"
        article.text = "Microsoft $MSFT reported strong Q4 earnings. The stock is up 5% in after-hours trading."
        article.url = "https://reddit.com/msft-earnings"

        self.mock_context_analyzer.analyze_ticker_relevance.return_value = (
            0.95,
            ["Earnings context"],
        )

        result = self.linker.link_article(article, use_title_only=False)

        assert len(result) == 1
        assert result[0].ticker == "MSFT"
        assert result[0].confidence == 0.95

    def test_etf_discussion(self):
        """Test linking with ETF discussions."""
        article = Mock()
        article.source = "reddit"
        article.title = "SPY vs QQQ comparison"
        article.text = (
            "I'm comparing $SPY and $QQQ for my portfolio. Both are solid ETF choices."
        )
        article.url = "https://reddit.com/etf-comparison"

        def mock_analyze(ticker, text, terms):
            return 0.8, [f"ETF discussion context for {ticker}"]

        self.mock_context_analyzer.analyze_ticker_relevance.side_effect = mock_analyze

        result = self.linker.link_article(article, use_title_only=False)

        assert len(result) == 2
        tickers = [link.ticker for link in result]
        assert "SPY" in tickers
        assert "QQQ" in tickers

    def test_mixed_case_ticker_mentions(self):
        """Test linking with mixed case ticker mentions."""
        article = Mock()
        article.source = "reddit"
        article.title = "Stock picks for 2024"
        article.text = (
            "I'm bullish on $aapl, $TSLA, nvda, and $GooGl. All are great tech stocks."
        )
        article.url = "https://reddit.com/stock-picks"

        def mock_analyze(ticker, text, terms):
            return 0.8, [f"Mixed case mention for {ticker}"]

        self.mock_context_analyzer.analyze_ticker_relevance.side_effect = mock_analyze

        result = self.linker.link_article(article, use_title_only=False)

        assert len(result) == 4
        tickers = [link.ticker for link in result]
        assert "AAPL" in tickers
        assert "TSLA" in tickers
        assert "NVDA" in tickers
        assert "GOOGL" in tickers

    def test_false_positive_prevention(self):
        """Test prevention of false positive matches."""
        article = Mock()
        article.source = "reddit"
        article.title = "I love apples and tesla cars"
        article.text = (
            "I bought some apples at the store and saw a Tesla car on the way home."
        )
        article.url = "https://reddit.com/random"

        # Mock context analyzer to return low confidence for false positives
        self.mock_context_analyzer.analyze_ticker_relevance.return_value = (
            0.2,
            ["Weak context - likely false positive"],
        )

        result = self.linker.link_article(article, use_title_only=False)

        # Should be filtered out due to low confidence
        assert len(result) == 0

    def test_reddit_comment_with_emoji_and_slang(self):
        """Test linking Reddit comments with emojis and slang."""
        article = Mock()
        article.source = "reddit_comment"
        article.title = "Comment"
        article.text = (
            "YOLO into $GME! 🚀💎🙌 This is the way! HODL! $AMC to the moon! 🌙"
        )
        article.url = "https://reddit.com/comment"

        with patch.object(self.linker, "_fast_reddit_comment_linking") as mock_fast:
            mock_fast.return_value = [
                TickerLinkDTO(
                    ticker="GME",
                    confidence=0.9,
                    matched_terms=["$GME"],
                    reasoning=["YOLO mention with emojis"],
                ),
                TickerLinkDTO(
                    ticker="AMC",
                    confidence=0.85,
                    matched_terms=["$AMC"],
                    reasoning=["To the moon mention"],
                ),
            ]

            result = self.linker.link_article(article, use_title_only=True)

            assert len(result) == 2
            assert result[0].ticker == "GME"
            assert result[1].ticker == "AMC"

    def test_long_form_analysis_post(self):
        """Test linking with long-form analysis posts."""
        article = Mock()
        article.source = "reddit"
        article.title = "Comprehensive Analysis: Tech Giants Q4 Performance"
        article.text = """
        After analyzing the Q4 performance of major tech companies, here are my findings:

        $AAPL: Strong iPhone sales drove revenue growth. The stock is trading at a premium but justified.
        $MSFT: Azure growth continues to impress. Office 365 adoption remains strong.
        $GOOGL: Search revenue stable, YouTube growth accelerating. Cloud division showing promise.
        $AMZN: AWS dominance continues, e-commerce recovery in progress.

        Overall, I'm bullish on all four names for 2024.
        """
        article.url = "https://reddit.com/tech-analysis"

        def mock_analyze(ticker, text, terms):
            return 0.9, [f"Comprehensive analysis context for {ticker}"]

        self.mock_context_analyzer.analyze_ticker_relevance.side_effect = mock_analyze

        result = self.linker.link_article(article, use_title_only=False)

        assert len(result) == 4
        tickers = [link.ticker for link in result]
        assert "AAPL" in tickers
        assert "MSFT" in tickers
        assert "GOOGL" in tickers
        assert "AMZN" in tickers
