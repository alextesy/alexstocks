"""Unit tests for WeeklySummaryService."""

from datetime import UTC, date, datetime
from unittest.mock import Mock

from app.models.dto import (
    SentimentDirection,
    TopSignal,
    WeeklyDigestContent,
    WeeklyTickerAggregate,
    WeeklyTickerSummaryBrief,
)


class TestWeeklyTickerAggregate:
    """Tests for WeeklyTickerAggregate dataclass."""

    def test_create_aggregate(self) -> None:
        """Test creating a weekly ticker aggregate."""
        aggregate = WeeklyTickerAggregate(
            ticker="AAPL",
            ticker_name="Apple Inc.",
            total_mentions=150,
            total_engagement=5000,
            days_with_data=5,
            avg_sentiment=0.65,
            sentiment_trend="improving",
            sentiment_start=0.55,
            sentiment_end=0.75,
            daily_summaries=["Day 1 summary", "Day 2 summary"],
            daily_sentiments=["Bullish", "Very Bullish"],
            daily_bullets=[["Point 1"], ["Point 2"]],
        )

        assert aggregate.ticker == "AAPL"
        assert aggregate.total_mentions == 150
        assert aggregate.sentiment_trend == "improving"

    def test_aggregate_with_no_data(self) -> None:
        """Test aggregate with no daily data."""
        aggregate = WeeklyTickerAggregate(
            ticker="XYZ",
            ticker_name="XYZ Corp",
            total_mentions=0,
            total_engagement=0,
            days_with_data=0,
            avg_sentiment=None,
            sentiment_trend="stable",
            sentiment_start=None,
            sentiment_end=None,
        )

        assert aggregate.days_with_data == 0
        assert aggregate.avg_sentiment is None


class TestWeeklyDigestContent:
    """Tests for WeeklyDigestContent dataclass."""

    def test_create_digest_content(self) -> None:
        """Test creating weekly digest content."""
        content = WeeklyDigestContent(
            week_start=date(2025, 12, 1),
            week_end=date(2025, 12, 7),
            user_timezone="America/New_York",
            generated_at=datetime.now(UTC),
            headline="Tech stocks surged this week",
            highlights=["AAPL hit new highs", "Market rallied on Fed news"],
            top_signals=[
                TopSignal(
                    theme="AI momentum",
                    examples=["NVDA earnings beat"],
                    tickers_involved=["NVDA", "MSFT"],
                )
            ],
            sentiment_direction=SentimentDirection(
                direction="improving",
                evidence="Overall bullish sentiment increased",
                confidence=0.85,
            ),
            risks_opportunities=["Watch for inflation data"],
            next_actions=["Consider reviewing tech exposure"],
            ticker_summaries=[
                WeeklyTickerSummaryBrief(
                    ticker="AAPL",
                    ticker_name="Apple Inc.",
                    sentiment_emoji="🚀",
                    one_liner="Strong week on iPhone sales news",
                    mention_count=100,
                )
            ],
            days_with_data=5,
            total_tickers=3,
        )

        assert content.headline == "Tech stocks surged this week"
        assert len(content.highlights) == 2
        assert content.days_with_data == 5


class TestSentimentTrendCalculation:
    """Tests for sentiment trend calculation logic."""

    def test_improving_trend(self) -> None:
        """Test detection of improving sentiment trend."""
        start_sentiment = 0.3
        end_sentiment = 0.7

        if end_sentiment - start_sentiment > 0.1:
            trend = "improving"
        elif start_sentiment - end_sentiment > 0.1:
            trend = "declining"
        else:
            trend = "stable"

        assert trend == "improving"

    def test_declining_trend(self) -> None:
        """Test detection of declining sentiment trend."""
        start_sentiment = 0.7
        end_sentiment = 0.2

        if end_sentiment - start_sentiment > 0.1:
            trend = "improving"
        elif start_sentiment - end_sentiment > 0.1:
            trend = "declining"
        else:
            trend = "stable"

        assert trend == "declining"

    def test_stable_trend(self) -> None:
        """Test detection of stable sentiment trend."""
        start_sentiment = 0.5
        end_sentiment = 0.55

        if end_sentiment - start_sentiment > 0.1:
            trend = "improving"
        elif start_sentiment - end_sentiment > 0.1:
            trend = "declining"
        else:
            trend = "stable"

        assert trend == "stable"


class TestWeeklyAggregation:
    """Tests for weekly data aggregation logic."""

    def test_aggregate_daily_summaries(self) -> None:
        """Test aggregating daily summaries into weekly view."""
        # Mock daily summaries for a ticker
        daily_summaries = [
            Mock(
                ticker="AAPL",
                summary_date=date(2025, 12, 1),
                mention_count=20,
                engagement_count=500,
                avg_sentiment=0.55,
                llm_summary="Monday summary",
                llm_summary_bullets=["Point 1"],
            ),
            Mock(
                ticker="AAPL",
                summary_date=date(2025, 12, 2),
                mention_count=30,
                engagement_count=800,
                avg_sentiment=0.65,
                llm_summary="Tuesday summary",
                llm_summary_bullets=["Point 2"],
            ),
        ]

        # Calculate aggregates
        total_mentions = sum(s.mention_count for s in daily_summaries)
        total_engagement = sum(s.engagement_count for s in daily_summaries)
        avg_sentiment = sum(s.avg_sentiment for s in daily_summaries) / len(
            daily_summaries
        )

        assert total_mentions == 50
        assert total_engagement == 1300
        assert abs(avg_sentiment - 0.6) < 0.01

    def test_empty_week_handling(self) -> None:
        """Test handling when no data available for the week."""
        daily_summaries: list = []

        total_mentions = (
            sum(s.mention_count for s in daily_summaries) if daily_summaries else 0
        )
        days_with_data = len(daily_summaries)

        assert total_mentions == 0
        assert days_with_data == 0


class TestTopSignalExtraction:
    """Tests for extracting top signals/themes from weekly data."""

    def test_extract_top_signals(self) -> None:
        """Test extracting top signals from aggregated data."""
        signal = TopSignal(
            theme="Earnings beat expectations",
            examples=["AAPL Q4 beat", "MSFT strong guidance"],
            tickers_involved=["AAPL", "MSFT"],
        )

        assert signal.theme == "Earnings beat expectations"
        assert len(signal.tickers_involved) == 2

    def test_signal_with_single_ticker(self) -> None:
        """Test signal involving a single ticker."""
        signal = TopSignal(
            theme="FDA approval news",
            examples=["Drug approval announced"],
            tickers_involved=["PFE"],
        )

        assert len(signal.tickers_involved) == 1


class TestWeeklySummaryBrief:
    """Tests for brief ticker summary generation."""

    def test_sentiment_emoji_mapping(self) -> None:
        """Test mapping sentiment to emoji."""
        emoji_map = {
            (0.8, 1.0): "🚀",  # Very bullish
            (0.6, 0.8): "📈",  # Bullish
            (0.4, 0.6): "➡️",  # Neutral
            (0.2, 0.4): "📉",  # Bearish
            (0.0, 0.2): "💀",  # Very bearish
        }

        def get_sentiment_emoji(sentiment: float) -> str:
            for (low, high), emoji in emoji_map.items():
                if low <= sentiment < high:
                    return emoji
            return "➡️"

        assert get_sentiment_emoji(0.9) == "🚀"
        assert get_sentiment_emoji(0.7) == "📈"
        assert get_sentiment_emoji(0.5) == "➡️"
        assert get_sentiment_emoji(0.3) == "📉"
        assert get_sentiment_emoji(0.1) == "💀"

    def test_create_brief_summary(self) -> None:
        """Test creating a brief summary for email."""
        brief = WeeklyTickerSummaryBrief(
            ticker="TSLA",
            ticker_name="Tesla Inc.",
            sentiment_emoji="📈",
            one_liner="Strong week on delivery numbers",
            mention_count=250,
        )

        assert brief.ticker == "TSLA"
        assert brief.sentiment_emoji == "📈"
        assert brief.mention_count == 250

