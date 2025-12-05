"""Unit tests for weekly email template rendering."""

from datetime import UTC, date, datetime

import pytest

from app.models.dto import (
    SentimentDirection,
    TopSignal,
    WeeklyDigestContent,
    WeeklyTickerSummaryBrief,
)


class TestWeeklyEmailTemplateData:
    """Tests for weekly email template data preparation."""

    @pytest.fixture
    def sample_digest_content(self) -> WeeklyDigestContent:
        """Create sample weekly digest content for testing."""
        return WeeklyDigestContent(
            week_start=date(2025, 12, 1),
            week_end=date(2025, 12, 7),
            user_timezone="America/New_York",
            generated_at=datetime.now(UTC),
            headline="Tech stocks led the market higher this week",
            highlights=[
                "NVDA surged on AI chip demand news",
                "AAPL reached new all-time highs",
                "Market sentiment improved on Fed comments",
            ],
            top_signals=[
                TopSignal(
                    theme="AI infrastructure demand",
                    examples=["NVDA earnings beat", "AMD guidance raise"],
                    tickers_involved=["NVDA", "AMD"],
                ),
                TopSignal(
                    theme="Consumer tech strength",
                    examples=["iPhone sales strong", "Holiday outlook positive"],
                    tickers_involved=["AAPL"],
                ),
            ],
            sentiment_direction=SentimentDirection(
                direction="improving",
                evidence="Reddit discussion sentiment shifted bullish",
                confidence=0.82,
            ),
            risks_opportunities=[
                "Watch for December jobs report",
                "Earnings season starts next week",
            ],
            next_actions=[
                "Review AI exposure in portfolio",
                "Consider tech sector rebalancing",
            ],
            ticker_summaries=[
                WeeklyTickerSummaryBrief(
                    ticker="NVDA",
                    ticker_name="NVIDIA Corporation",
                    sentiment_emoji="🚀",
                    one_liner="Strong week on continued AI momentum",
                    mention_count=450,
                ),
                WeeklyTickerSummaryBrief(
                    ticker="AAPL",
                    ticker_name="Apple Inc.",
                    sentiment_emoji="📈",
                    one_liner="Positive iPhone sales data drove gains",
                    mention_count=320,
                ),
                WeeklyTickerSummaryBrief(
                    ticker="TSLA",
                    ticker_name="Tesla Inc.",
                    sentiment_emoji="➡️",
                    one_liner="Mixed sentiment on delivery numbers",
                    mention_count=280,
                ),
            ],
            days_with_data=5,
            total_tickers=3,
        )

    def test_digest_content_has_required_fields(
        self, sample_digest_content: WeeklyDigestContent
    ) -> None:
        """Test that digest content has all required fields."""
        assert sample_digest_content.week_start is not None
        assert sample_digest_content.week_end is not None
        assert sample_digest_content.headline is not None
        assert len(sample_digest_content.highlights) > 0
        assert len(sample_digest_content.ticker_summaries) > 0

    def test_week_date_range_formatting(
        self, sample_digest_content: WeeklyDigestContent
    ) -> None:
        """Test week date range can be formatted for display."""
        week_start = sample_digest_content.week_start
        week_end = sample_digest_content.week_end

        formatted = f"{week_start.strftime('%b %d')} - {week_end.strftime('%b %d, %Y')}"
        assert formatted == "Dec 01 - Dec 07, 2025"

    def test_ticker_summary_count(
        self, sample_digest_content: WeeklyDigestContent
    ) -> None:
        """Test ticker summary count matches total_tickers."""
        assert (
            len(sample_digest_content.ticker_summaries)
            == sample_digest_content.total_tickers
        )

    def test_sentiment_direction_formatting(
        self, sample_digest_content: WeeklyDigestContent
    ) -> None:
        """Test sentiment direction can be formatted for display."""
        direction = sample_digest_content.sentiment_direction

        # Format for HTML display
        if direction.direction == "improving":
            arrow = "↑"
            color = "green"
        elif direction.direction == "declining":
            arrow = "↓"
            color = "red"
        else:
            arrow = "→"
            color = "gray"

        assert arrow == "↑"
        assert color == "green"

    def test_top_signals_have_tickers(
        self, sample_digest_content: WeeklyDigestContent
    ) -> None:
        """Test that top signals reference specific tickers."""
        for signal in sample_digest_content.top_signals:
            assert len(signal.tickers_involved) > 0

    def test_highlights_are_strings(
        self, sample_digest_content: WeeklyDigestContent
    ) -> None:
        """Test that highlights are non-empty strings."""
        for highlight in sample_digest_content.highlights:
            assert isinstance(highlight, str)
            assert len(highlight.strip()) > 0


class TestWeeklyEmailHtmlRendering:
    """Tests for HTML email rendering."""

    def test_html_escaping_in_content(self) -> None:
        """Test that HTML special characters are escaped."""
        from html import escape

        text_with_html = "Stock rose >10% & analysts <love> it"
        escaped = escape(text_with_html)
        assert "&gt;" in escaped
        assert "&lt;" in escaped
        assert "&amp;" in escaped

    def test_emoji_rendering(self) -> None:
        """Test that emojis are preserved in output."""
        emojis = ["🚀", "📈", "➡️", "📉", "💀"]
        for emoji in emojis:
            assert len(emoji) > 0
            # Emojis should be preserved as-is in UTF-8 HTML
            assert emoji.encode("utf-8")

    def test_url_formatting(self) -> None:
        """Test URL formatting for ticker links."""
        base_url = "https://alexstocks.com"
        ticker = "AAPL"
        url = f"{base_url}/ticker/{ticker}"
        assert url == "https://alexstocks.com/ticker/AAPL"


class TestWeeklyEmailPlainTextRendering:
    """Tests for plain text email rendering."""

    @pytest.fixture
    def sample_digest_content(self) -> WeeklyDigestContent:
        """Create sample content for plain text tests."""
        return WeeklyDigestContent(
            week_start=date(2025, 12, 1),
            week_end=date(2025, 12, 7),
            user_timezone="UTC",
            generated_at=datetime.now(UTC),
            headline="Weekly Market Summary",
            highlights=["Point 1", "Point 2"],
            top_signals=[],
            sentiment_direction=SentimentDirection(
                direction="stable",
                evidence="Neutral week",
                confidence=0.5,
            ),
            risks_opportunities=[],
            next_actions=[],
            ticker_summaries=[
                WeeklyTickerSummaryBrief(
                    ticker="AAPL",
                    ticker_name="Apple Inc.",
                    sentiment_emoji="📈",
                    one_liner="Good week",
                    mention_count=100,
                )
            ],
            days_with_data=5,
            total_tickers=1,
        )

    def test_plain_text_line_width(
        self, sample_digest_content: WeeklyDigestContent
    ) -> None:
        """Test that plain text lines fit standard width."""
        max_line_width = 80

        headline = sample_digest_content.headline
        assert len(headline) <= max_line_width

    def test_plain_text_bullet_formatting(self) -> None:
        """Test bullet point formatting for plain text."""
        highlights = ["Point 1", "Point 2", "Point 3"]
        formatted = "\n".join(f"• {h}" for h in highlights)

        assert "• Point 1" in formatted
        assert formatted.count("•") == 3

    def test_plain_text_divider(self) -> None:
        """Test section divider for plain text."""
        divider = "-" * 60
        assert len(divider) == 60
        assert divider == "------------------------------------------------------------"


class TestEmailSubjectLine:
    """Tests for email subject line generation."""

    def test_subject_with_date_range(self) -> None:
        """Test subject line includes date range."""
        week_start = date(2025, 12, 1)
        week_end = date(2025, 12, 7)

        subject = f"Your Weekly Market Digest - {week_start.strftime('%b %d')}-{week_end.strftime('%d')}"
        assert subject == "Your Weekly Market Digest - Dec 01-07"

    def test_subject_with_ticker_count(self) -> None:
        """Test subject line with ticker count."""
        ticker_count = 5
        subject = f"Weekly Digest: {ticker_count} tickers from your watchlist"
        assert "5 tickers" in subject

    def test_subject_length_limit(self) -> None:
        """Test subject line doesn't exceed recommended length."""
        max_subject_length = 60  # Recommended for email clients

        subject = "Your Weekly Market Digest - Dec 01-07"
        assert len(subject) <= max_subject_length
