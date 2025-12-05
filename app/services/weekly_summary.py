"""Weekly ticker summary service for generating weekly digest content."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

from langchain.chat_models import init_chat_model
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.config import settings
from app.db.models import Ticker
from app.models.dto import (
    DailyTickerSummaryDTO,
    SentimentDirection,
    TopSignal,
    WeeklyDigestContent,
    WeeklyTickerAggregate,
    WeeklyTickerSummaryBrief,
)
from app.repos.summary_repo import DailyTickerSummaryRepository
from app.repos.user_repo import UserRepository
from app.services.email_utils import map_sentiment_to_display

logger = logging.getLogger(__name__)


class TopSignalItem(BaseModel):
    """A single top signal/theme from the week."""

    theme: str = Field(description="The theme or pattern identified")
    examples: list[str] = Field(description="Examples supporting this theme")
    tickers_involved: list[str] = Field(description="Tickers related to this theme")


class TickerSummaryItem(BaseModel):
    """A brief summary for a single ticker."""

    ticker: str = Field(description="The ticker symbol")
    sentiment_emoji: str = Field(
        description=(
            "Sentiment emoji: 🚀 (very bullish), 📈 (bullish), ➡️ (neutral), "
            "📉 (bearish), 💀 (very bearish)"
        )
    )
    one_liner: str = Field(description="One-line summary of the ticker's week")


class WeeklySummaryInfo(BaseModel):
    """Structured response model for LLM weekly synthesis."""

    headline: str = Field(
        description=(
            "A compelling 10-15 word headline summarizing the week's most important "
            "market theme for the user's watchlist."
        )
    )
    highlights: list[str] = Field(
        description=(
            "3-5 key highlights synthesizing the week's activity across all tickers. "
            "Focus on themes and patterns, not day-by-day recaps."
        )
    )
    top_signals: list[TopSignalItem] = Field(
        description=(
            "2-3 top signals/themes. Each signal should identify a pattern "
            "that emerged across the week."
        )
    )
    sentiment_direction: str = Field(
        description=(
            "Overall sentiment trend for the week: 'improving', 'stable', or 'declining'. "
            "Based on comparing early week vs late week sentiment."
        )
    )
    sentiment_evidence: str = Field(
        description="Brief explanation supporting the sentiment direction assessment."
    )
    risks_opportunities: list[str] = Field(
        description=(
            "1-3 items to watch next week based on this week's patterns. "
            "Include both risks and opportunities."
        )
    )
    next_actions: list[str] = Field(
        description="1-3 actionable suggestions for the user based on the week's activity."
    )
    ticker_summaries: list[TickerSummaryItem] = Field(
        description="Brief summary for each ticker."
    )


@dataclass
class WeekBoundaries:
    """ISO week date boundaries."""

    week_start: date  # Monday
    week_end: date  # Sunday


def get_week_boundaries(reference_date: date | None = None) -> WeekBoundaries:
    """Get week boundaries for the last 7 days.

    Args:
        reference_date: Reference date to calculate from (defaults to today)

    Returns:
        WeekBoundaries with start as 7 days ago, end as yesterday
    """
    if reference_date is None:
        reference_date = date.today()

    # Last 7 days: from 7 days ago to yesterday
    week_end = reference_date - timedelta(days=1)  # Yesterday
    week_start = week_end - timedelta(days=6)  # 7 days total

    return WeekBoundaries(week_start=week_start, week_end=week_end)


class WeeklySummaryService:
    """Service that aggregates daily summaries and generates weekly digest content."""

    def __init__(self, session: Session) -> None:
        """Initialize the service.

        Args:
            session: Database session
        """
        self._session = session
        self._summary_repo = DailyTickerSummaryRepository(session)
        self._user_repo = UserRepository(session)

    def aggregate_weekly_summaries(
        self,
        tickers: list[str],
        week_start: date,
        week_end: date,
    ) -> list[WeeklyTickerAggregate]:
        """Aggregate daily summaries for tickers over a week.

        Args:
            tickers: List of ticker symbols to aggregate
            week_start: Start of week (Monday)
            week_end: End of week (Sunday)

        Returns:
            List of WeeklyTickerAggregate with aggregated data per ticker
        """
        if not tickers:
            return []

        # Get all daily summaries for the week
        summaries_by_ticker = self._summary_repo.get_summaries_for_week(
            tickers=tickers, week_start=week_start, week_end=week_end
        )

        # Get ticker names from database
        ticker_names = self._get_ticker_names(tickers)

        aggregates: list[WeeklyTickerAggregate] = []

        for ticker in tickers:
            daily_summaries = summaries_by_ticker.get(ticker, [])
            if not daily_summaries:
                continue

            aggregate = self._build_aggregate(
                ticker=ticker,
                ticker_name=ticker_names.get(ticker, ticker),
                daily_summaries=daily_summaries,
            )
            aggregates.append(aggregate)

        # Sort by total mentions descending
        aggregates.sort(key=lambda a: a.total_mentions, reverse=True)

        return aggregates

    def _build_aggregate(
        self,
        ticker: str,
        ticker_name: str,
        daily_summaries: list[DailyTickerSummaryDTO],
    ) -> WeeklyTickerAggregate:
        """Build aggregate data for a single ticker."""
        total_mentions = sum(s.mention_count for s in daily_summaries)
        total_engagement = sum(s.engagement_count for s in daily_summaries)
        days_with_data = len(daily_summaries)

        # Calculate average sentiment
        sentiments = [
            s.avg_sentiment for s in daily_summaries if s.avg_sentiment is not None
        ]
        avg_sentiment = sum(sentiments) / len(sentiments) if sentiments else None

        # Calculate sentiment trend
        sentiment_start = daily_summaries[0].avg_sentiment if daily_summaries else None
        sentiment_end = daily_summaries[-1].avg_sentiment if daily_summaries else None
        sentiment_trend = self._calculate_sentiment_trend(
            sentiment_start, sentiment_end
        )

        # Collect daily summaries and bullets
        daily_summary_texts = [
            s.llm_summary or "" for s in daily_summaries if s.llm_summary
        ]
        daily_sentiment_labels = [
            s.llm_sentiment.value if s.llm_sentiment else "neutral"
            for s in daily_summaries
        ]
        daily_bullets = [s.llm_summary_bullets or [] for s in daily_summaries]

        # Get dominant sentiment category for the week
        dominant_sentiment = self._get_dominant_sentiment(daily_sentiment_labels)

        return WeeklyTickerAggregate(
            ticker=ticker,
            ticker_name=ticker_name,
            total_mentions=total_mentions,
            total_engagement=total_engagement,
            days_with_data=days_with_data,
            avg_sentiment=avg_sentiment,
            sentiment_trend=sentiment_trend,
            sentiment_start=sentiment_start,
            sentiment_end=sentiment_end,
            dominant_sentiment=dominant_sentiment,
            daily_summaries=daily_summary_texts,
            daily_sentiments=daily_sentiment_labels,
            daily_bullets=daily_bullets,
        )

    def _calculate_sentiment_trend(self, start: float | None, end: float | None) -> str:
        """Calculate sentiment trend direction."""
        if start is None or end is None:
            return "stable"

        diff = end - start
        if diff > 0.1:
            return "improving"
        elif diff < -0.1:
            return "declining"
        return "stable"

    def _get_ticker_names(self, tickers: list[str]) -> dict[str, str]:
        """Get ticker names from database."""
        if not tickers:
            return {}

        result = (
            self._session.query(Ticker.symbol, Ticker.name)
            .filter(Ticker.symbol.in_(tickers))
            .all()
        )
        return {row.symbol: row.name for row in result}

    def generate_weekly_digest(
        self,
        aggregates: list[WeeklyTickerAggregate],
        week_start: date,
        week_end: date,
        user_timezone: str = "UTC",
        max_tickers: int | None = None,
    ) -> WeeklyDigestContent:
        """Generate weekly digest content using LLM synthesis.

        Args:
            aggregates: Aggregated ticker data for the week
            week_start: Start of week
            week_end: End of week
            user_timezone: User's timezone for display
            max_tickers: Maximum tickers to include (defaults to config)

        Returns:
            WeeklyDigestContent ready for email rendering
        """
        max_tickers = max_tickers or settings.weekly_digest_max_tickers_per_user

        if not aggregates:
            return self._empty_digest(week_start, week_end, user_timezone)

        # Limit tickers
        limited_aggregates = aggregates[:max_tickers]

        # Build prompt and call LLM
        try:
            llm_response = self._generate_llm_synthesis(
                limited_aggregates, week_start, week_end
            )
        except Exception as e:
            logger.error(
                "LLM synthesis failed, using fallback",
                extra={"error": str(e)},
                exc_info=True,
            )
            return self._fallback_digest(
                limited_aggregates, week_start, week_end, user_timezone
            )

        return self._build_digest_from_llm(
            llm_response=llm_response,
            aggregates=limited_aggregates,
            week_start=week_start,
            week_end=week_end,
            user_timezone=user_timezone,
        )

    def _generate_llm_synthesis(
        self,
        aggregates: list[WeeklyTickerAggregate],
        week_start: date,
        week_end: date,
    ) -> WeeklySummaryInfo:
        """Generate LLM synthesis of weekly data."""
        api_key = settings.openai_api_key
        if not api_key:
            raise ValueError("OPENAI_API_KEY is required for weekly digest")

        prompt = self._build_weekly_prompt(aggregates, week_start, week_end)

        model = init_chat_model(
            settings.weekly_digest_llm_model,
            temperature=settings.weekly_digest_llm_temperature,
            timeout=30,
            max_tokens=settings.weekly_digest_llm_max_tokens,
            api_key=api_key,
        )

        structured_model = model.with_structured_output(WeeklySummaryInfo)

        logger.info(
            "Invoking LLM for weekly synthesis",
            extra={
                "model": settings.weekly_digest_llm_model,
                "num_tickers": len(aggregates),
                "prompt_length": len(prompt),
            },
        )

        response = structured_model.invoke(prompt)

        if not isinstance(response, WeeklySummaryInfo):
            raise ValueError(f"Unexpected response type: {type(response)}")

        return response

    def _build_weekly_prompt(
        self,
        aggregates: list[WeeklyTickerAggregate],
        week_start: date,
        week_end: date,
    ) -> str:
        """Build prompt for weekly LLM synthesis."""
        week_display = (
            f"{week_start.strftime('%B %d')} - {week_end.strftime('%B %d, %Y')}"
        )

        system_prompt = (
            "You are an expert financial analyst specializing in synthesizing market sentiment "
            "and trends for retail investors. Your task is to analyze a week's worth of daily "
            "summaries and create a cohesive weekly narrative.\n\n"
            "IMPORTANT: Do NOT simply repeat day-by-day summaries. Instead:\n"
            "- Identify patterns and themes that emerged across the week\n"
            "- Synthesize insights that weren't visible in individual daily summaries\n"
            "- Highlight the most significant developments\n"
            "- Provide actionable context for the coming week"
        )

        ticker_data = []
        for agg in aggregates:
            ticker_section = [
                f"\n## {agg.ticker} ({agg.ticker_name})",
                f"Weekly Stats: {agg.total_mentions} mentions, {agg.days_with_data} days of data",
                f"Sentiment Trend: {agg.sentiment_trend}",
            ]

            if agg.avg_sentiment is not None:
                ticker_section.append(f"Avg Sentiment: {agg.avg_sentiment:.2f}")

            # Add daily summaries (condensed)
            if agg.daily_summaries:
                ticker_section.append("\nDaily Highlights:")
                for i, summary in enumerate(agg.daily_summaries[:5]):  # Limit to 5 days
                    # Truncate each summary
                    truncated = summary[:300] + "..." if len(summary) > 300 else summary
                    ticker_section.append(f"  Day {i + 1}: {truncated}")

            ticker_data.append("\n".join(ticker_section))

        lines = [
            system_prompt,
            "",
            f"Week: {week_display}",
            f"Tickers analyzed: {len(aggregates)}",
            "",
            "--- TICKER DATA ---",
            "\n".join(ticker_data),
            "",
            "--- END TICKER DATA ---",
            "",
            "Generate a weekly synthesis that helps the investor understand the overall "
            "market mood and key developments for their watchlist this week.",
        ]

        return "\n".join(lines)

    def _build_digest_from_llm(
        self,
        llm_response: WeeklySummaryInfo,
        aggregates: list[WeeklyTickerAggregate],
        week_start: date,
        week_end: date,
        user_timezone: str,
    ) -> WeeklyDigestContent:
        """Build WeeklyDigestContent from LLM response."""
        # Parse top signals (now proper Pydantic models)
        top_signals = [
            TopSignal(
                theme=signal.theme,
                examples=signal.examples,
                tickers_involved=signal.tickers_involved,
            )
            for signal in llm_response.top_signals[:3]
        ]

        # Parse sentiment direction
        sentiment_direction = SentimentDirection(
            direction=llm_response.sentiment_direction,
            evidence=llm_response.sentiment_evidence,
            confidence=0.8,  # Default confidence
        )

        # Build ticker summaries from LLM response + aggregates
        ticker_summaries = []
        llm_ticker_map = {ts.ticker: ts for ts in llm_response.ticker_summaries}

        for agg in aggregates:
            llm_summary = llm_ticker_map.get(agg.ticker)
            # Use dominant sentiment category to get emoji (same as daily email)
            sentiment_emoji = self._get_sentiment_emoji_from_category(
                agg.dominant_sentiment
            )
            # Only use LLM emoji if it's valid
            if llm_summary and self._is_valid_emoji(llm_summary.sentiment_emoji):
                sentiment_emoji = llm_summary.sentiment_emoji

            ticker_summaries.append(
                WeeklyTickerSummaryBrief(
                    ticker=agg.ticker,
                    ticker_name=agg.ticker_name,
                    sentiment_emoji=sentiment_emoji,
                    one_liner=(
                        llm_summary.one_liner
                        if llm_summary
                        else f"{agg.total_mentions} mentions this week"
                    ),
                    mention_count=agg.total_mentions,
                )
            )

        return WeeklyDigestContent(
            week_start=week_start,
            week_end=week_end,
            user_timezone=user_timezone,
            generated_at=datetime.now(UTC),
            headline=llm_response.headline,
            highlights=llm_response.highlights[:5],
            top_signals=top_signals,
            sentiment_direction=sentiment_direction,
            risks_opportunities=llm_response.risks_opportunities[:3],
            next_actions=llm_response.next_actions[:3],
            ticker_summaries=ticker_summaries,
            days_with_data=(
                max(agg.days_with_data for agg in aggregates) if aggregates else 0
            ),
            total_tickers=len(aggregates),
        )

    def _fallback_digest(
        self,
        aggregates: list[WeeklyTickerAggregate],
        week_start: date,
        week_end: date,
        user_timezone: str,
    ) -> WeeklyDigestContent:
        """Generate fallback digest without LLM."""
        ticker_summaries = [
            WeeklyTickerSummaryBrief(
                ticker=agg.ticker,
                ticker_name=agg.ticker_name,
                sentiment_emoji=self._get_sentiment_emoji_from_category(
                    agg.dominant_sentiment
                ),
                one_liner=f"{agg.total_mentions} mentions, sentiment {agg.sentiment_trend}",
                mention_count=agg.total_mentions,
            )
            for agg in aggregates
        ]

        # Calculate overall sentiment trend
        trends = [agg.sentiment_trend for agg in aggregates]
        if trends.count("improving") > trends.count("declining"):
            overall_direction = "improving"
        elif trends.count("declining") > trends.count("improving"):
            overall_direction = "declining"
        else:
            overall_direction = "stable"

        return WeeklyDigestContent(
            week_start=week_start,
            week_end=week_end,
            user_timezone=user_timezone,
            generated_at=datetime.now(UTC),
            headline=f"Your Weekly Market Update: {len(aggregates)} Tickers Analyzed",
            highlights=[
                f"Tracked {sum(a.total_mentions for a in aggregates)} total mentions",
                f"Overall sentiment trend: {overall_direction}",
            ],
            top_signals=[],
            sentiment_direction=SentimentDirection(
                direction=overall_direction,
                evidence="Based on aggregate sentiment trends",
                confidence=0.5,
            ),
            risks_opportunities=[],
            next_actions=[],
            ticker_summaries=ticker_summaries,
            days_with_data=(
                max(agg.days_with_data for agg in aggregates) if aggregates else 0
            ),
            total_tickers=len(aggregates),
        )

    def _empty_digest(
        self, week_start: date, week_end: date, user_timezone: str
    ) -> WeeklyDigestContent:
        """Generate empty digest when no data available."""
        return WeeklyDigestContent(
            week_start=week_start,
            week_end=week_end,
            user_timezone=user_timezone,
            generated_at=datetime.now(UTC),
            headline="No Activity This Week",
            highlights=["No significant activity for your watchlist this week."],
            top_signals=[],
            sentiment_direction=SentimentDirection(
                direction="stable",
                evidence="No data available",
                confidence=0.0,
            ),
            risks_opportunities=[],
            next_actions=[
                "Add more tickers to your watchlist for richer weekly digests."
            ],
            ticker_summaries=[],
            days_with_data=0,
            total_tickers=0,
        )

    def _get_dominant_sentiment(self, sentiment_labels: list[str]) -> str:
        """Get the most common sentiment category from daily summaries."""
        if not sentiment_labels:
            return "neutral"

        # Count occurrences
        from collections import Counter

        counts = Counter(sentiment_labels)
        # Return the most common, defaulting to neutral
        most_common = counts.most_common(1)
        return most_common[0][0] if most_common else "neutral"

    def _get_sentiment_emoji_from_category(self, sentiment_category: str) -> str:
        """Get emoji using the same mapping as daily emails."""
        display = map_sentiment_to_display(sentiment_category)
        return display.emoji

    def _get_sentiment_emoji(self, sentiment: float | None) -> str:
        """Map sentiment score to emoji (fallback for numerical scores)."""
        if sentiment is None:
            return "⚖️"  # Neutral

        # FinBERT scores are typically -1 to +1
        if sentiment >= 0.5:
            return "🚀"  # Extreme positive
        elif sentiment >= 0.2:
            return "📈"  # Positive
        elif sentiment >= -0.2:
            return "⚖️"  # Neutral
        elif sentiment >= -0.5:
            return "📉"  # Negative
        else:
            return "💀"  # Extreme negative

    def _is_valid_emoji(self, text: str) -> bool:
        """Check if text is a valid sentiment emoji."""
        valid_emojis = {"🚀", "📈", "⚖️", "➡️", "📉", "💀", "🔥", "⚠️", "✅", "📊"}
        # Strip whitespace and check if it's one of our valid emojis
        stripped = text.strip()
        return stripped in valid_emojis or (
            len(stripped) <= 4 and any(ord(c) > 127 for c in stripped)
        )
