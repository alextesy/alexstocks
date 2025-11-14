"""Jinja-based email template rendering service."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, date, datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.config import settings
from app.models.dto import (
    DailyTickerSummaryDTO,
    UserDTO,
    UserProfileDTO,
    UserTickerFollowDTO,
)
from app.services.email_utils import (
    build_unsubscribe_url,
    ensure_plain_text,
    format_summary_date,
    map_sentiment_to_display,
    normalize_article_payload,
)


class EmailTemplateService:
    """Service responsible for rendering email templates."""

    HTML_TEMPLATE = "daily_briefing.html"
    TEXT_TEMPLATE = "daily_briefing.txt"

    def __init__(self, template_dir: str | Path | None = None):
        base_path = Path(template_dir or Path("app") / "templates" / "email")
        self.template_dir = base_path
        loader = FileSystemLoader(str(base_path))
        self._html_env = Environment(
            loader=loader,
            autoescape=select_autoescape(["html", "xml"]),
        )
        self._text_env = Environment(loader=loader, autoescape=False)

    def render_daily_briefing(
        self,
        user: UserDTO,
        user_profile: UserProfileDTO | None,
        ticker_summaries: Sequence[DailyTickerSummaryDTO],
        unsubscribe_token: str,
        user_ticker_follows: Sequence[UserTickerFollowDTO] | None = None,
    ) -> tuple[str, str]:
        """Render HTML and plain-text daily briefing emails."""
        context = self._build_context(
            user=user,
            user_profile=user_profile,
            ticker_summaries=ticker_summaries,
            unsubscribe_token=unsubscribe_token,
            user_ticker_follows=user_ticker_follows,
        )
        html = self._html_env.get_template(self.HTML_TEMPLATE).render(**context)
        text = self._text_env.get_template(self.TEXT_TEMPLATE).render(**context)
        return html, text

    def render_basic_summary(
        self, ticker_summaries: Sequence[DailyTickerSummaryDTO]
    ) -> tuple[str, str]:
        """Fallback formatter used when personalization data is unavailable."""
        if not ticker_summaries:
            return "", ""

        sorted_summaries = sorted(
            ticker_summaries,
            key=lambda x: x.engagement_count,
            reverse=True,
        )

        html_parts = [
            "<h1>Market Pulse Daily Summary</h1>",
            "<p>Here's your daily market intelligence:</p>",
            "<table style='border-collapse: collapse; width: 100%;'>",
            "<tr style='background-color: #f2f2f2;'>",
            "<th style='border: 1px solid #ddd; padding: 8px; text-align: left;'>Ticker</th>",
            "<th style='border: 1px solid #ddd; padding: 8px; text-align: left;'>Mentions</th>",
            "<th style='border: 1px solid #ddd; padding: 8px; text-align: left;'>Engagement</th>",
            "<th style='border: 1px solid #ddd; padding: 8px; text-align: left;'>Sentiment</th>",
            "</tr>",
        ]

        text_parts = [
            "Market Pulse Daily Summary",
            "=" * 30,
            "",
            "Here's your daily market intelligence:",
            "",
            f"{'Ticker':<10} {'Mentions':<10} {'Engagement':<12} {'Sentiment'}",
            "-" * 60,
        ]

        for summary in sorted_summaries:
            sentiment_display = "N/A"
            if summary.llm_sentiment:
                sentiment_display = summary.llm_sentiment.value.title()

            html_parts.extend(
                [
                    "<tr>",
                    f"<td style='border: 1px solid #ddd; padding: 8px;'>{summary.ticker}</td>",
                    f"<td style='border: 1px solid #ddd; padding: 8px;'>{summary.mention_count}</td>",
                    f"<td style='border: 1px solid #ddd; padding: 8px;'>{summary.engagement_count}</td>",
                    f"<td style='border: 1px solid #ddd; padding: 8px;'>{sentiment_display}</td>",
                    "</tr>",
                ]
            )

            text_parts.append(
                f"{summary.ticker:<10} {summary.mention_count:<10} {summary.engagement_count:<12} {sentiment_display}"
            )

            if summary.llm_summary:
                html_parts.append(
                    f"<tr><td colspan='4' style='border: 1px solid #ddd; padding: 8px;'><strong>Summary:</strong> {summary.llm_summary}</td></tr>"
                )
                text_parts.append(f"Summary: {summary.llm_summary}")
                text_parts.append("")

        html_parts.extend(["</table>", "<p>Stay informed with Market Pulse!</p>"])
        text_parts.extend(["", "Stay informed with Market Pulse!"])

        return "\n".join(html_parts), "\n".join(text_parts)

    def _build_context(
        self,
        *,
        user: UserDTO,
        user_profile: UserProfileDTO | None,
        ticker_summaries: Sequence[DailyTickerSummaryDTO],
        unsubscribe_token: str,
        user_ticker_follows: Sequence[UserTickerFollowDTO] | None,
    ) -> dict:
        timezone = user_profile.timezone if user_profile else None
        summary_date = self._resolve_summary_date(ticker_summaries)
        tickers = self._prepare_tickers(ticker_summaries, user_ticker_follows)

        context = {
            "user": {
                "display_name": user_profile.display_name if user_profile else None,
                "email": user.email,
            },
            "date": summary_date,
            "date_display": format_summary_date(summary_date, timezone),
            "timezone": timezone or settings.daily_summary_window_timezone,
            "tickers": tickers,
            "has_tickers": bool(tickers),
            "unsubscribe_url": build_unsubscribe_url(unsubscribe_token),
            "company_name": settings.email_company_name,
            "company_address": settings.email_company_address,
            "support_email": settings.email_from_address,
            "app_base_url": settings.app_base_url,
            "ticker_limit": settings.email_daily_briefing_max_tickers,
            "articles_limit": settings.email_daily_briefing_max_articles,
            "generated_at": datetime.now(UTC),
        }
        return context

    def _prepare_tickers(
        self,
        ticker_summaries: Sequence[DailyTickerSummaryDTO],
        user_ticker_follows: Sequence[UserTickerFollowDTO] | None,
    ) -> list[dict]:
        if not ticker_summaries:
            return []

        follow_map = {
            follow.ticker.upper(): follow for follow in user_ticker_follows or []
        }

        records: list[tuple[DailyTickerSummaryDTO, UserTickerFollowDTO | None]] = []
        for summary in ticker_summaries:
            ticker_key = summary.ticker.upper()
            follow = follow_map.get(ticker_key)
            if follow_map and follow is None:
                # User provided watchlist; skip tickers they do not follow
                continue
            records.append((summary, follow))

        if follow_map:
            records.sort(key=lambda pair: pair[1].order if pair[1] else 0)
        else:
            records.sort(key=lambda pair: pair[0].engagement_count, reverse=True)

        limited = records[: settings.email_daily_briefing_max_tickers]
        return [self._hydrate_ticker(summary, follow) for summary, follow in limited]

    def _hydrate_ticker(
        self,
        summary: DailyTickerSummaryDTO,
        follow: UserTickerFollowDTO | None,
    ) -> dict:
        sentiment = map_sentiment_to_display(summary.llm_sentiment)
        articles = self._normalize_articles(summary.top_articles)
        summary_text = summary.llm_summary or ""
        bullets = summary.llm_summary_bullets or []
        bullets_plain = []
        for bullet in bullets:
            cleaned = ensure_plain_text(bullet)
            if cleaned:
                bullets_plain.append(cleaned)

        return {
            "symbol": summary.ticker,
            "name": (
                follow.ticker_name if follow and follow.ticker_name else summary.ticker
            ),
            "sentiment": sentiment.key,
            "sentiment_label": sentiment.label,
            "sentiment_text_label": sentiment.text_label,
            "sentiment_emoji": sentiment.emoji,
            "sentiment_color": sentiment.color,
            "summary": summary_text,
            "summary_plain": ensure_plain_text(summary_text),
            "bullets": bullets,
            "bullets_plain": bullets_plain,
            "mention_count": summary.mention_count,
            "engagement_count": summary.engagement_count,
            "avg_sentiment": summary.avg_sentiment,
            "top_articles": articles,
            "follow_order": follow.order if follow else None,
        }

    def _normalize_articles(self, articles_raw) -> list[dict]:
        normalized: list[dict] = []
        if not articles_raw:
            return normalized

        for article in articles_raw:
            normalized_article = normalize_article_payload(article)
            if not normalized_article:
                continue
            normalized.append(normalized_article)
            if len(normalized) >= settings.email_daily_briefing_max_articles:
                break

        return normalized

    @staticmethod
    def _resolve_summary_date(
        ticker_summaries: Sequence[DailyTickerSummaryDTO],
    ) -> date | None:
        dates = [
            summary.summary_date for summary in ticker_summaries if summary.summary_date
        ]
        if not dates:
            return None
        return max(dates)
