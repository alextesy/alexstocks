"""Tests for GDELT ingestion functionality."""

from datetime import UTC, datetime

from app.db.models import Article, Ticker
from ingest.linker import TickerLinker
from ingest.parser import extract_url, parse_gdelt_date, parse_gdelt_gkg_csv


class TestGDELTParser:
    """Test GDELT CSV parser functionality."""

    def test_parse_gdelt_date(self):
        """Test GDELT date parsing."""
        # Valid date
        date_str = "20240101120000"
        result = parse_gdelt_date(date_str)
        expected = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)
        assert result == expected

        # Invalid date should return current time
        invalid_date = "invalid"
        result = parse_gdelt_date(invalid_date)
        assert isinstance(result, datetime)
        assert result.tzinfo == UTC

    def test_extract_url(self):
        """Test URL extraction from document identifier."""
        # Valid URL
        assert (
            extract_url("https://example.com/article") == "https://example.com/article"
        )
        assert extract_url("http://example.com/article") == "http://example.com/article"

        # Invalid cases
        assert extract_url("#") is None
        assert extract_url("") is None
        assert extract_url(None) is None

    def test_parse_gdelt_gkg_csv(self):
        """Test parsing GDELT GKG CSV content."""
        # Sample GDELT GKG CSV content
        csv_content = """GKGRECORDID,DATE,SourceCollectionIdentifier,SourceCommonName,DocumentIdentifier,Counts,V2Counts,Themes,V2Themes,Locations,V2Locations,Persons,V2Persons,Organizations,V2Organizations,V2Tone,V2EnhancedDates,V2GCAM,V2SharingImage,V2RelatedImages,V2SocialImageEmbeds,V2SocialVideoEmbeds,V2Quotations,V2AllNames,V2Amounts,V2TranslationInfo,V2ExtrasXML
1234567890,20240101120000,1,Reuters,https://reuters.com/article1,,,,,,,,,,,,,,,,,,,,,,,,
1234567891,20240101120000,1,Bloomberg,https://bloomberg.com/article2,,,,,,,,,,,,,,,,,,,,,,,,"""

        articles = parse_gdelt_gkg_csv(csv_content)

        assert len(articles) == 2

        # Check first article
        article1 = articles[0]
        assert article1.source == "gdelt"
        assert article1.url == "https://reuters.com/article1"
        assert article1.published_at == datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)
        assert "reuters.com" in article1.title

        # Check second article
        article2 = articles[1]
        assert article2.source == "gdelt"
        assert article2.url == "https://bloomberg.com/article2"
        assert article2.published_at == datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)
        assert "bloomberg.com" in article2.title


class TestTickerLinker:
    """Test ticker linking functionality."""

    def test_ticker_linker_initialization(self):
        """Test TickerLinker initialization."""
        tickers = [
            Ticker(
                symbol="AAPL", name="Apple Inc", aliases=["aapl", "apple", "apple inc"]
            ),
            Ticker(
                symbol="MSFT",
                name="Microsoft Corporation",
                aliases=["msft", "microsoft"],
            ),
        ]

        linker = TickerLinker(tickers)

        # Check alias mapping
        assert linker.alias_to_ticker["aapl"] == "AAPL"
        assert linker.alias_to_ticker["apple"] == "AAPL"
        assert linker.alias_to_ticker["msft"] == "MSFT"
        assert linker.alias_to_ticker["microsoft"] == "MSFT"

    def test_link_article(self):
        """Test article-ticker linking."""
        tickers = [
            Ticker(
                symbol="AAPL", name="Apple Inc", aliases=["aapl", "apple", "apple inc"]
            ),
            Ticker(
                symbol="MSFT",
                name="Microsoft Corporation",
                aliases=["msft", "microsoft"],
            ),
        ]

        linker = TickerLinker(tickers)

        # Test article with ticker mentions
        article = Article(
            source="gdelt",
            url="https://example.com/apple-news",
            published_at=datetime.now(UTC),
            title="Apple Inc reports strong earnings",
            text="Apple Inc (AAPL) reported strong quarterly earnings. The company's stock price rose significantly.",
        )

        article_tickers = linker.link_article(article)

        assert len(article_tickers) >= 1
        assert any(at.ticker == "AAPL" for at in article_tickers)

        # Check confidence scores
        for at in article_tickers:
            assert 0.0 <= at.confidence <= 1.0

    def test_link_article_with_dollar_symbol(self):
        """Test article linking with $SYMBOL format."""
        tickers = [
            Ticker(symbol="AAPL", name="Apple Inc", aliases=["aapl", "apple"]),
        ]

        linker = TickerLinker(tickers)

        article = Article(
            source="gdelt",
            url="https://example.com/stock-news",
            published_at=datetime.now(UTC),
            title="Stock Market Update",
            text="$AAPL is trading higher today.",
        )

        article_tickers = linker.link_article(article)

        assert len(article_tickers) == 1
        assert article_tickers[0].ticker == "AAPL"
        assert article_tickers[0].confidence > 0.8  # High confidence for $SYMBOL format
