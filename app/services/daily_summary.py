"""Daily ticker summary service for generating LLM-ready prompts."""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta
from typing import Any, Literal
from zoneinfo import ZoneInfo

from langchain.chat_models import init_chat_model
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import settings
from app.db.models import Article, ArticleTicker, Ticker

logger = logging.getLogger(__name__)

Framework = Literal["langchain", "langgraph"]


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
        upvote_weight: float = 0.7,
        comment_weight: float = 0.3,
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

        window_text = (
            f"Analyze retail investor sentiment for {ticker_summary.ticker} from "
            f"{window_start:%Y-%m-%d %H:%M} UTC through {window_end:%Y-%m-%d %H:%M} UTC."
        )
        instructions = (
            "Provide two concise paragraphs: one covering momentum and sentiment, "
            "another capturing the most cited catalysts."
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

    def build_langgraph_payload(self, summary: DailySummaryResult) -> dict[str, Any]:
        """Build a payload for LangGraph orchestrations."""

        api_key = settings.openai_api_key
        if not api_key:
            raise ValueError("OPENAI_API_KEY is required for LangGraph payloads")

        payload = {
            "framework": "langgraph",
            "config": {
                "llm": {
                    "provider": "openai",
                    "model": settings.daily_summary_llm_model,
                },
                "credentials": {"openai_api_key": api_key},
            },
            "input": {
                "prompt": self.build_prompt(summary),
                "context": self._serialize_summary(summary),
            },
        }
        logger.debug(
            "Constructed LangGraph payload",
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
    ) -> list[str]:
        """Execute the configured LangChain model with one prompt per ticker using batch calls.

        Args:
            summary: DailySummaryResult with tickers to summarize
            max_concurrency: Maximum number of parallel API calls (default: 5)

        Returns:
            List of responses, one per ticker in the same order as summary.tickers
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
            "Invoking LangChain model with batch calls",
            extra={
                "model": model_name,
                "api_key_preview": masked_key,
                "num_tickers": len(prompts),
                "max_concurrency": max_concurrency,
                "avg_prompt_length": (
                    sum(len(p) for p in prompts) // len(prompts) if prompts else 0
                ),
            },
        )

        model = init_chat_model(
            model_name,
            temperature=settings.daily_summary_llm_temperature,
            timeout=settings.daily_summary_llm_timeout_seconds,
            max_tokens=settings.daily_summary_llm_max_tokens,
            api_key=api_key,
        )

        try:
            # LangChain's batch accepts list[str] (prompts), but mypy types are strict
            responses = model.batch(prompts, config={"max_concurrency": max_concurrency})  # type: ignore[arg-type]
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

        outputs: list[str] = []
        for idx, response in enumerate(responses):
            content = getattr(response, "content", None)
            if isinstance(content, str):
                outputs.append(content)
            elif isinstance(content, list):
                concatenated = "".join(
                    part.get("text", "") if isinstance(part, dict) else str(part)
                    for part in content
                )
                outputs.append(concatenated)
            else:
                outputs.append(str(response))

            logger.debug(
                "Received response for ticker",
                extra={
                    "ticker": (
                        ticker_symbols[idx] if idx < len(ticker_symbols) else "unknown"
                    ),
                    "response_length": len(outputs[-1]),
                },
            )

        logger.info(
            "Completed batch LangChain calls",
            extra={
                "num_responses": len(outputs),
                "tickers": ticker_symbols,
            },
        )

        return outputs

    def _engagement_score(self, article: Article, confidence: float | None) -> float:
        upvotes = max(0, int(article.upvotes or 0))
        comments = max(0, int(article.num_comments or 0))
        conf = max(0.0, float(confidence or 1.0))

        score = self._upvote_weight * math.log1p(
            upvotes
        ) + self._comment_weight * math.log1p(comments)
        return score * conf

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
