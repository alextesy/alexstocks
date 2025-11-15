"""Daily ticker summary service for generating LLM-ready prompts."""

from __future__ import annotations

import json
import logging
import math
import re
from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta
from typing import Any, Literal
from zoneinfo import ZoneInfo

from langchain.chat_models import init_chat_model
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import settings
from app.db.models import Article, ArticleTicker, LLMSentimentCategory, Ticker
from app.services.engagement import (
    DEFAULT_COMMENT_WEIGHT,
    DEFAULT_UPVOTE_WEIGHT,
    calculate_engagement_score,
)

logger = logging.getLogger(__name__)

Framework = Literal["langchain", "langgraph"]


class SummaryInfo(BaseModel):
    """Structured response model for LLM summary with sentiment classification."""

    summary: str = Field(
        description=(
            "Two concise paragraphs: one covering momentum and sentiment, "
            "another capturing the most cited catalysts."
        )
    )
    sentiment: LLMSentimentCategory = Field(
        description=(
            "Overall sentiment classification for the ticker based on retail investor discussions. "
            "Choose the category that best represents the collective mood:\n"
            "- 🚀 To the Moon: Extreme positive sentiment - hype, euphoric, bullish calls like 'buy the dip', "
            "'diamond hands', 'this is going 10x', emojis 🚀💎🙌\n"
            "- Bullish: Optimistic or confident sentiment, but not extreme - 'looks good', "
            "'earnings should beat', 'undervalued'\n"
            "- Neutral: Factual, news-driven, or uncertain tone - 'earnings report tomorrow', "
            "'holding for now', 'need to see volume'\n"
            "- Bearish: Skeptical or mildly negative tone - 'overvalued', 'will drop', 'I'm selling'\n"
            "- 💀 Doom: Extreme negative sentiment - panic or mockery - 'bagholders', 'dead company', "
            "'GG', 'rip portfolio', emojis 💀😬😭"
        )
    )


@dataclass(frozen=True)
class ParsedLLMResponse:
    """Parsed structured response from LLM."""

    summary: str
    sentiment: LLMSentimentCategory | None


def parse_llm_response(response: str) -> ParsedLLMResponse:
    """Parse structured JSON response from LLM.

    Args:
        response: Raw response string from LLM (may contain JSON or plain text)

    Returns:
        ParsedLLMResponse with summary text and sentiment category

    The function attempts to:
    1. Extract JSON from the response (handles markdown code blocks, extra text)
    2. Parse the JSON and extract summary and sentiment fields
    3. Validate sentiment category
    4. Fall back to storing raw response if parsing fails
    """
    if not response or not response.strip():
        return ParsedLLMResponse(summary="", sentiment=None)

    # Try to extract JSON from response (may be wrapped in markdown code blocks)
    json_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", response, re.DOTALL)
    if json_match:
        json_str = json_match.group(1)
    else:
        # Try to find JSON object directly
        json_match = re.search(r"\{.*\}", response, re.DOTALL)
        if json_match:
            json_str = json_match.group(0)
        else:
            # No JSON found, return raw response as summary
            logger.warning(
                "No JSON found in LLM response, storing raw text",
                extra={"response_preview": response[:200]},
            )
            return ParsedLLMResponse(summary=response.strip(), sentiment=None)

    try:
        parsed = json.loads(json_str)
        summary_text = parsed.get("summary", "").strip()
        sentiment_raw = parsed.get("sentiment", "").strip()

        # Map variations to enum values (case-insensitive for text, preserve emojis)
        sentiment_mapping = {
            "🚀 to the moon": LLMSentimentCategory.TO_THE_MOON,
            "to the moon": LLMSentimentCategory.TO_THE_MOON,
            "bullish": LLMSentimentCategory.BULLISH,
            "neutral": LLMSentimentCategory.NEUTRAL,
            "bearish": LLMSentimentCategory.BEARISH,
            "💀 doom": LLMSentimentCategory.DOOM,
            "doom": LLMSentimentCategory.DOOM,
        }

        # First check exact match (case-sensitive) against enum values
        sentiment_category: LLMSentimentCategory | None = None
        try:
            sentiment_category = LLMSentimentCategory(sentiment_raw)
        except ValueError:
            # If no exact match, try normalized (lowercase) version
            sentiment_normalized = sentiment_raw.lower()
            sentiment_category = sentiment_mapping.get(sentiment_normalized)

        if not sentiment_category:
            logger.warning(
                "Invalid sentiment category in LLM response",
                extra={
                    "sentiment_received": sentiment_raw,
                    "valid_sentiments": [cat.value for cat in LLMSentimentCategory],
                },
            )

        # Return enum directly (or None if invalid)
        return ParsedLLMResponse(summary=summary_text, sentiment=sentiment_category)

    except json.JSONDecodeError as e:
        logger.warning(
            "Failed to parse JSON from LLM response, storing raw text",
            extra={"error": str(e), "json_preview": json_str[:200]},
        )
        return ParsedLLMResponse(summary=response.strip(), sentiment=None)


@dataclass(frozen=True)
class DailySummaryArticle:
    """Lightweight article representation used for summaries."""

    article_id: int
    ticker: str
    title: str
    url: str
    text: str | None
    published_at: datetime
    upvotes: int
    num_comments: int
    engagement_score: float
    confidence: float
    source: str
    matched_terms: tuple[str, ...]
    sentiment: float | None
    subreddit: str | None
    author: str | None


@dataclass(frozen=True)
class DailyTickerSummary:
    """Aggregated view of mentions and ranked articles for a ticker."""

    ticker: str
    mentions: int
    articles: list[DailySummaryArticle]


@dataclass(frozen=True)
class DailySummaryResult:
    """Container for the complete summary payload."""

    window_start: datetime
    window_end: datetime
    tickers: list[DailyTickerSummary]
    total_mentions: int
    total_ranked_articles: int


class DailySummaryService:
    """Service that prepares LLM prompts for the previous UTC day."""

    def __init__(
        self,
        session: Session,
        *,
        articles_per_ticker: int = 10,
        upvote_weight: float = DEFAULT_UPVOTE_WEIGHT,
        comment_weight: float = DEFAULT_COMMENT_WEIGHT,
    ) -> None:
        self._session = session
        self._articles_per_ticker = max(1, articles_per_ticker)
        self._upvote_weight = upvote_weight
        self._comment_weight = comment_weight

    def load_previous_day_summary(
        self, max_tickers: int | None = None
    ) -> DailySummaryResult:
        """Load mention and article data for the previous UTC day.

        Args:
            max_tickers: Maximum number of tickers to include. If None, uses
                settings.daily_summary_max_tickers. Useful for testing.
        """

        window_start, window_end = self._summary_window()
        logger.debug(
            "Computing daily summary window",
            extra={
                "window_start": window_start.isoformat(),
                "window_end": window_end.isoformat(),
                "max_tickers": max_tickers,
            },
        )

        top_tickers = self._fetch_top_tickers(window_start, window_end, max_tickers)
        if not top_tickers:
            logger.info(
                "No tickers met daily summary thresholds",
                extra={
                    "window_start": window_start.isoformat(),
                    "window_end": window_end.isoformat(),
                },
            )
            return DailySummaryResult(
                window_start=window_start,
                window_end=window_end,
                tickers=[],
                total_mentions=0,
                total_ranked_articles=0,
            )

        articles = self._fetch_articles_for_tickers(
            top_tickers, window_start, window_end
        )

        ticker_summaries: list[DailyTickerSummary] = []
        total_mentions = 0
        total_ranked_articles = 0

        for ticker_symbol, mentions in top_tickers:
            ranked_articles = [
                article for article in articles if article.ticker == ticker_symbol
            ]
            ranked_articles.sort(
                key=lambda article: article.engagement_score, reverse=True
            )
            limited_articles = ranked_articles[: self._articles_per_ticker]

            ticker_summaries.append(
                DailyTickerSummary(
                    ticker=ticker_symbol,
                    mentions=mentions,
                    articles=limited_articles,
                )
            )
            total_mentions += mentions
            total_ranked_articles += len(limited_articles)

        return DailySummaryResult(
            window_start=window_start,
            window_end=window_end,
            tickers=ticker_summaries,
            total_mentions=total_mentions,
            total_ranked_articles=total_ranked_articles,
        )

    def load_custom_summary(
        self,
        window_start: datetime,
        window_end: datetime,
        max_tickers: int | None = None,
    ) -> DailySummaryResult:
        """Load summary data for a custom time window and ticker count.

        Args:
            window_start: Start of the time window (UTC-aware datetime)
            window_end: End of the time window (UTC-aware datetime)
            max_tickers: Maximum number of tickers to include. If None, uses
                the configured default from settings.

        Returns:
            DailySummaryResult with tickers and articles for the specified window.
        """
        window_start = self._ensure_utc(window_start)
        window_end = self._ensure_utc(window_end)

        logger.debug(
            "Computing custom daily summary window",
            extra={
                "window_start": window_start.isoformat(),
                "window_end": window_end.isoformat(),
                "max_tickers": max_tickers,
            },
        )

        top_tickers = self._fetch_top_tickers(window_start, window_end, max_tickers)
        if not top_tickers:
            logger.info(
                "No tickers met daily summary thresholds",
                extra={
                    "window_start": window_start.isoformat(),
                    "window_end": window_end.isoformat(),
                },
            )
            return DailySummaryResult(
                window_start=window_start,
                window_end=window_end,
                tickers=[],
                total_mentions=0,
                total_ranked_articles=0,
            )

        articles = self._fetch_articles_for_tickers(
            top_tickers, window_start, window_end
        )

        ticker_summaries: list[DailyTickerSummary] = []
        total_mentions = 0
        total_ranked_articles = 0

        for ticker_symbol, mentions in top_tickers:
            ranked_articles = [
                article for article in articles if article.ticker == ticker_symbol
            ]
            ranked_articles.sort(
                key=lambda article: article.engagement_score, reverse=True
            )
            limited_articles = ranked_articles[: self._articles_per_ticker]

            ticker_summaries.append(
                DailyTickerSummary(
                    ticker=ticker_symbol,
                    mentions=mentions,
                    articles=limited_articles,
                )
            )
            total_mentions += mentions
            total_ranked_articles += len(limited_articles)

        return DailySummaryResult(
            window_start=window_start,
            window_end=window_end,
            tickers=ticker_summaries,
            total_mentions=total_mentions,
            total_ranked_articles=total_ranked_articles,
        )

    def build_prompt_for_ticker(
        self,
        ticker_summary: DailyTickerSummary,
        window_start: datetime,
        window_end: datetime,
    ) -> str:
        """Construct a natural language prompt for a single ticker."""

        # System prompt explaining the model's role
        system_prompt = (
            "You are an expert social networks and financial analyst specializing in "
            "assessing market sentiment and ambience around stocks based on articles "
            "from various sources including Reddit, news outlets, and other social media platforms. "
            "Your role is to analyze the collective sentiment, identify key themes and catalysts, "
            "and provide insights into how retail investors and the broader market perceive "
            "different stocks."
        )

        # Format date as "November 7th" or "November 7"
        trading_date = window_end.date()
        month_name = trading_date.strftime("%B")
        day = trading_date.day
        day_suffix = (
            "th" if 11 <= day <= 13 else {1: "st", 2: "nd", 3: "rd"}.get(day % 10, "th")
        )
        year = trading_date.year
        start_text = window_start.astimezone(
            ZoneInfo(settings.daily_summary_window_timezone)
        )
        end_text = window_end.astimezone(
            ZoneInfo(settings.daily_summary_window_timezone)
        )
        window_range = (
            f"{start_text.strftime('%B %d, %Y %I:%M %p %Z')} to "
            f"{end_text.strftime('%B %d, %Y %I:%M %p %Z')}"
        )

        window_text = (
            f"Analyze retail investor sentiment for {ticker_summary.ticker} "
            f"during the previous trading window ({window_range}). "
            f"The summary must reflect discussions specific to {month_name} {day}{day_suffix}, {year}."
        )
        instructions = (
            "Analyze the provided articles and synthesize a comprehensive summary. "
            "Your response must be structured as JSON with 'summary' and 'sentiment' fields.\n\n"
            "Summary: Write two concise paragraphs - the first should cover momentum and overall sentiment "
            "trends, the second should capture the most cited catalysts and key themes.\n\n"
            "Sentiment: Classify the overall retail investor sentiment by analyzing the collective tone, "
            "language patterns, and emotional indicators across all discussions. Consider the intensity and "
            "consistency of sentiment signals, not just isolated comments.\n\n"
            "Be explicit that findings apply to the specified date only. Do not reference earlier years unless "
            "directly compared as part of that day's discussion."
        )

        lines = [
            system_prompt,
            "",
            window_text,
            instructions,
            "",
            f"Ticker: {ticker_summary.ticker} — {ticker_summary.mentions} mentions",
            "",
            "Use the engagement-weighted highlights below. Articles are sorted by engagement score.",
        ]

        # Group articles by subreddit
        articles_by_subreddit: dict[str | None, list[DailySummaryArticle]] = {}
        for article in ticker_summary.articles:
            subreddit = article.subreddit
            if subreddit not in articles_by_subreddit:
                articles_by_subreddit[subreddit] = []
            articles_by_subreddit[subreddit].append(article)

        # Sort subreddits by total engagement (sum of engagement scores)
        sorted_subreddits = sorted(
            articles_by_subreddit.items(),
            key=lambda x: sum(a.engagement_score for a in x[1]),
            reverse=True,
        )

        for subreddit, articles in sorted_subreddits:
            if subreddit:
                lines.append(f"\nSubreddit: r/{subreddit}")
            else:
                lines.append("\nSubreddit: (none)")

            for article in articles:
                # Use text if available, otherwise fall back to empty string
                article_text = article.text or ""
                if not article_text.strip():
                    continue

                # Only show score, no other metadata
                lines.append(f" - Score {article.engagement_score:.2f}:")
                # Truncate text if too long (limit to ~500 chars)
                display_text = article_text[:500]
                if len(article_text) > 500:
                    display_text += "..."
                lines.append(f"   {display_text}")

        lines.append(
            "\nFocus on facts from the sources and avoid speculation or investment advice."
        )

        return "\n".join(lines)

    def build_prompt(self, summary: DailySummaryResult) -> str:
        """Construct a natural language prompt for all tickers (legacy method)."""

        if not summary.tickers:
            return (
                "You are a financial assistant for Market Pulse. "
                "No tickers met the mention thresholds in the previous UTC day. "
                "Respond with a brief note that no summary is available."
            )

        # For backward compatibility, build prompts for all tickers
        prompts = []
        for ticker_summary in summary.tickers:
            prompt = self.build_prompt_for_ticker(
                ticker_summary, summary.window_start, summary.window_end
            )
            prompts.append(prompt)

        # Join with separator
        return "\n\n" + "=" * 80 + "\n\n".join(prompts)

    def build_langchain_payload(self, summary: DailySummaryResult) -> dict[str, Any]:
        """Build a payload consumable by LangChain runners."""

        api_key = settings.openai_api_key
        if not api_key:
            raise ValueError("OPENAI_API_KEY is required for LangChain payloads")

        payload = {
            "framework": "langchain",
            "llm": {
                "provider": "openai",
                "model": settings.daily_summary_llm_model,
                "api_key": api_key,
            },
            "prompt": self.build_prompt(summary),
            "metadata": self._serialize_summary(summary),
        }
        logger.debug(
            "Constructed LangChain payload",
            extra={
                "tickers": len(summary.tickers),
                "articles": summary.total_ranked_articles,
            },
        )
        return payload

    def _summary_window(self) -> tuple[datetime, datetime]:
        try:
            tz = ZoneInfo(settings.daily_summary_window_timezone)
        except Exception as exc:  # pragma: no cover - invalid tz configs should be rare
            raise ValueError(
                f"Invalid timezone for daily summary: {settings.daily_summary_window_timezone}"
            ) from exc

        now_local = datetime.now(tz)
        target_date = now_local.date() - timedelta(days=1)

        start_hour = settings.daily_summary_window_start_hour
        end_hour = settings.daily_summary_window_end_hour
        start_local = datetime.combine(target_date, time(hour=start_hour), tzinfo=tz)
        end_local = datetime.combine(target_date, time(hour=end_hour), tzinfo=tz)

        if end_local <= start_local:
            end_local += timedelta(days=1)

        return start_local.astimezone(UTC), end_local.astimezone(UTC)

    def _fetch_top_tickers(
        self,
        window_start: datetime,
        window_end: datetime,
        max_tickers: int | None = None,
    ) -> list[tuple[str, int]]:
        min_mentions = max(1, settings.daily_summary_min_mentions)
        max_tickers = max(1, max_tickers or settings.daily_summary_max_tickers)

        rows = (
            self._session.query(
                func.upper(ArticleTicker.ticker).label("ticker"),
                func.count(ArticleTicker.article_id).label("mentions"),
            )
            .join(Article, Article.id == ArticleTicker.article_id)
            .join(Ticker, Ticker.symbol == ArticleTicker.ticker)
            .filter(
                Article.published_at >= window_start,
                Article.published_at < window_end,
                ~Ticker.name.like("%ETF%"),
            )
            .group_by(func.upper(ArticleTicker.ticker))
            .having(func.count(ArticleTicker.article_id) >= min_mentions)
            .order_by(func.count(ArticleTicker.article_id).desc())
            .limit(max_tickers * 3)
            .all()
        )

        top_tickers: list[tuple[str, int]] = []
        for row in rows:
            ticker = str(row.ticker).upper()
            mentions = int(row.mentions or 0)
            if mentions >= min_mentions:
                top_tickers.append((ticker, mentions))
            if len(top_tickers) >= max_tickers:
                break

        logger.debug(
            "Top tickers for daily summary",
            extra={"tickers": top_tickers, "min_mentions": min_mentions},
        )
        return top_tickers

    def _fetch_articles_for_tickers(
        self,
        tickers_with_counts: list[tuple[str, int]],
        window_start: datetime,
        window_end: datetime,
    ) -> list[DailySummaryArticle]:
        tickers = [ticker for ticker, _ in tickers_with_counts]
        rows = (
            self._session.query(
                Article,
                func.upper(ArticleTicker.ticker).label("ticker"),
                ArticleTicker.confidence,
                ArticleTicker.matched_terms,
            )
            .join(ArticleTicker, Article.id == ArticleTicker.article_id)
            .filter(
                func.upper(ArticleTicker.ticker).in_(tickers),
                Article.published_at >= window_start,
                Article.published_at < window_end,
            )
            .all()
        )

        articles: list[DailySummaryArticle] = []
        for article, ticker, confidence, matched_terms in rows:
            engagement = self._engagement_score(article, confidence)
            normalized_terms: tuple[str, ...] = ()
            if matched_terms:
                normalized_terms = tuple(str(term) for term in matched_terms if term)
            articles.append(
                DailySummaryArticle(
                    article_id=int(article.id),
                    ticker=str(ticker).upper(),
                    title=article.title,
                    url=article.url,
                    text=article.text,
                    published_at=self._ensure_utc(article.published_at),
                    upvotes=int(article.upvotes or 0),
                    num_comments=int(article.num_comments or 0),
                    engagement_score=engagement,
                    confidence=float(confidence or 0.0),
                    source=article.source,
                    matched_terms=normalized_terms,
                    sentiment=(
                        float(article.sentiment)
                        if article.sentiment is not None
                        else None
                    ),
                    subreddit=article.subreddit,
                    author=article.author,
                )
            )

        logger.debug(
            "Fetched articles for summary",
            extra={"count": len(articles), "tickers": tickers},
        )
        return articles

    def generate_langchain_summary(
        self, summary: DailySummaryResult, max_concurrency: int = 5
    ) -> list[SummaryInfo]:
        """Execute the configured LangChain model with one prompt per ticker using batch calls.

        Args:
            summary: DailySummaryResult with tickers to summarize
            max_concurrency: Maximum number of parallel API calls (default: 5)

        Returns:
            List of SummaryInfo objects, one per ticker in the same order as summary.tickers
        """

        if not summary.tickers:
            return []

        api_key = settings.openai_api_key
        if not api_key:
            raise ValueError("OPENAI_API_KEY is required to invoke LangChain")

        model_name = settings.daily_summary_llm_model

        # Build a prompt for each ticker
        prompts: list[str] = []
        ticker_symbols: list[str] = []
        for ticker_summary in summary.tickers:
            prompt = self.build_prompt_for_ticker(
                ticker_summary, summary.window_start, summary.window_end
            )
            prompts.append(prompt)
            ticker_symbols.append(ticker_summary.ticker)

        # Mask API key for logging (show first 7 and last 4 chars)
        masked_key = f"{api_key[:7]}...{api_key[-4:]}" if len(api_key) > 11 else "***"
        logger.info(
            "Invoking LangChain model with structured output",
            extra={
                "model": model_name,
                "api_key_preview": masked_key,
                "num_tickers": len(prompts),
                "max_concurrency": max_concurrency,
                "avg_prompt_length": (
                    sum(len(p) for p in prompts) // len(prompts) if prompts else 0
                ),
                "response_format": "SummaryInfo",
            },
        )

        model = init_chat_model(
            model_name,
            temperature=settings.daily_summary_llm_temperature,
            timeout=settings.daily_summary_llm_timeout_seconds,
            max_tokens=settings.daily_summary_llm_max_tokens,
            api_key=api_key,
        )

        # Configure structured output using Pydantic model
        structured_model = model.with_structured_output(SummaryInfo)

        try:
            # Use structured output - responses will be SummaryInfo objects
            from typing import cast

            responses = structured_model.batch(  # type: ignore[attr-defined]
                cast(Any, prompts), config={"max_concurrency": max_concurrency}
            )
        except Exception as e:
            error_msg = str(e)
            error_type = type(e).__name__

            # Provide helpful error messages for common issues
            if (
                "quota" in error_msg.lower()
                or "insufficient_quota" in error_msg.lower()
            ):
                logger.error(
                    "OpenAI API quota error",
                    extra={
                        "error_type": error_type,
                        "error_message": error_msg,
                        "api_key_preview": masked_key,
                        "model": model_name,
                    },
                )
                raise RuntimeError(
                    f"OpenAI API quota exceeded. Error: {error_msg}\n"
                    f"API Key preview: {masked_key}\n"
                    f"Model: {model_name}\n"
                    "Please check your OpenAI account billing and quota at https://platform.openai.com/account/billing"
                ) from e
            elif "rate_limit" in error_msg.lower() or "429" in error_msg:
                logger.error(
                    "OpenAI API rate limit error",
                    extra={
                        "error_type": error_type,
                        "error_message": error_msg,
                        "api_key_preview": masked_key,
                        "model": model_name,
                    },
                )
                raise RuntimeError(
                    f"OpenAI API rate limit exceeded. Error: {error_msg}\n"
                    f"API Key preview: {masked_key}\n"
                    f"Model: {model_name}\n"
                    "Please wait a moment and try again, or check your rate limits at https://platform.openai.com/account/limits"
                ) from e
            else:
                logger.error(
                    "OpenAI API error",
                    extra={
                        "error_type": error_type,
                        "error_message": error_msg,
                        "api_key_preview": masked_key,
                        "model": model_name,
                    },
                )
                raise RuntimeError(
                    f"OpenAI API error ({error_type}): {error_msg}\n"
                    f"API Key preview: {masked_key}\n"
                    f"Model: {model_name}"
                ) from e

        # Responses are already SummaryInfo objects from structured output
        summary_infos: list[SummaryInfo] = []
        for idx, response in enumerate(responses):
            # Ensure response is SummaryInfo (should be from structured output)
            if isinstance(response, SummaryInfo):
                summary_infos.append(response)
            else:
                # Fallback: try to parse if somehow we got a string
                logger.warning(
                    "Unexpected response type, attempting to parse",
                    extra={
                        "ticker": (
                            ticker_symbols[idx]
                            if idx < len(ticker_symbols)
                            else "unknown"
                        ),
                        "response_type": type(response).__name__,
                    },
                )
                # This shouldn't happen with structured output, but handle gracefully
                parsed = parse_llm_response(str(response))
                # Use parsed sentiment enum, default to Neutral if None
                sentiment_enum = parsed.sentiment or LLMSentimentCategory.NEUTRAL
                summary_infos.append(
                    SummaryInfo(summary=parsed.summary, sentiment=sentiment_enum)
                )

            logger.debug(
                "Received response for ticker",
                extra={
                    "ticker": (
                        ticker_symbols[idx] if idx < len(ticker_symbols) else "unknown"
                    ),
                    "sentiment": summary_infos[-1].sentiment,
                },
            )

        logger.info(
            "Completed batch LangChain calls",
            extra={
                "num_responses": len(summary_infos),
                "tickers": ticker_symbols,
            },
        )

        return summary_infos

    def _engagement_score(self, article: Article, confidence: float | None) -> float:
        conf = max(0.0, float(confidence or 1.0))
        base_score = article.engagement_score
        weights_match_defaults = math.isclose(
            self._upvote_weight, DEFAULT_UPVOTE_WEIGHT
        ) and math.isclose(self._comment_weight, DEFAULT_COMMENT_WEIGHT)

        if base_score is None or not weights_match_defaults:
            base_score = calculate_engagement_score(
                article.upvotes,
                article.num_comments,
                upvote_weight=self._upvote_weight,
                comment_weight=self._comment_weight,
            )

        return float(base_score) * conf

    def _ensure_utc(self, published_at: datetime) -> datetime:
        if published_at.tzinfo is None:
            return published_at.replace(tzinfo=UTC)
        return published_at.astimezone(UTC)

    def _serialize_summary(self, summary: DailySummaryResult) -> dict[str, Any]:
        return {
            "window_start": summary.window_start.isoformat(),
            "window_end": summary.window_end.isoformat(),
            "total_mentions": summary.total_mentions,
            "total_ranked_articles": summary.total_ranked_articles,
            "tickers": [
                {
                    "ticker": ticker_summary.ticker,
                    "mentions": ticker_summary.mentions,
                    "articles": [
                        {
                            "article_id": article.article_id,
                            "title": article.title,
                            "url": article.url,
                            "text": article.text,
                            "published_at": article.published_at.isoformat(),
                            "upvotes": article.upvotes,
                            "num_comments": article.num_comments,
                            "engagement_score": article.engagement_score,
                            "confidence": article.confidence,
                            "source": article.source,
                            "matched_terms": list(article.matched_terms),
                            "sentiment": article.sentiment,
                            "subreddit": article.subreddit,
                            "author": article.author,
                        }
                        for article in ticker_summary.articles
                    ],
                }
                for ticker_summary in summary.tickers
            ],
        }
