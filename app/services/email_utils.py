"""Utility helpers for building email content."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time
from typing import Any
from urllib.parse import quote_plus, urljoin
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.config import settings
from app.db.models import LLMSentimentCategory


@dataclass(frozen=True)
class SentimentDisplay:
    """Presentation metadata for a sentiment value."""

    key: str
    label: str
    emoji: str
    color: str
    text_label: str


_SENTIMENT_MAP: dict[str, SentimentDisplay] = {
    "extreme_positive": SentimentDisplay(
        key="extreme_positive",
        label="🚀 To the Moon (Extreme Positive)",
        emoji="🚀",
        color="#15803d",
        text_label="To the Moon (Extreme Positive)",
    ),
    "positive": SentimentDisplay(
        key="positive",
        label="Bullish (Positive)",
        emoji="📈",
        color="#16a34a",
        text_label="Bullish (Positive)",
    ),
    "neutral": SentimentDisplay(
        key="neutral",
        label="Neutral",
        emoji="⚖️",
        color="#6b7280",
        text_label="Neutral",
    ),
    "negative": SentimentDisplay(
        key="negative",
        label="Bearish (Negative)",
        emoji="📉",
        color="#dc2626",
        text_label="Bearish (Negative)",
    ),
    "extreme_negative": SentimentDisplay(
        key="extreme_negative",
        label="💀 Doom (Extreme Negative)",
        emoji="💀",
        color="#991b1b",
        text_label="Doom (Extreme Negative)",
    ),
}

_DEFAULT_SENTIMENT = _SENTIMENT_MAP["neutral"]

_SENTIMENT_ALIASES: dict[str, str] = {
    "🚀 to the moon": "extreme_positive",
    "to the moon": "extreme_positive",
    "bullish": "positive",
    "neutral": "neutral",
    "bearish": "negative",
    "💀 doom": "extreme_negative",
    "doom": "extreme_negative",
}


def map_sentiment_to_display(
    value: str | LLMSentimentCategory | None,
) -> SentimentDisplay:
    """Map stored sentiment value to presentation metadata."""
    if value is None:
        return _DEFAULT_SENTIMENT

    if isinstance(value, LLMSentimentCategory):
        normalized = value.value.lower()
    else:
        normalized = value.lower()

    if normalized in _SENTIMENT_MAP:
        return _SENTIMENT_MAP[normalized]

    alias = _SENTIMENT_ALIASES.get(normalized)
    if alias and alias in _SENTIMENT_MAP:
        return _SENTIMENT_MAP[alias]

    return _DEFAULT_SENTIMENT


def format_summary_date(summary_date: date | None, timezone: str | None) -> str:
    """Format summary date in the recipient's timezone."""
    try:
        summary_tz = ZoneInfo(settings.daily_summary_window_timezone)
    except ZoneInfoNotFoundError:
        summary_tz = ZoneInfo("UTC")

    try:
        target_tz = ZoneInfo(timezone) if timezone else summary_tz
    except ZoneInfoNotFoundError:
        target_tz = summary_tz

    if summary_date is None:
        summary_date = datetime.now(summary_tz).date()

    anchor = datetime.combine(summary_date, time(hour=12), tzinfo=summary_tz)
    localized = anchor.astimezone(target_tz)
    return localized.strftime("%A, %B %d, %Y")


def build_unsubscribe_url(token: str) -> str:
    """Generate unsubscribe URL from base URL and signed token."""
    base_url = settings.app_base_url.rstrip("/")
    encoded = quote_plus(token)
    return urljoin(f"{base_url}/", f"unsubscribe?token={encoded}")


def ensure_plain_text(value: str | None) -> str:
    """Ensure string is safe for the plain-text template."""
    if not value:
        return ""
    # Replace unicode bullets/dashes with ASCII equivalents
    cleaned = (
        value.replace("•", "-")
        .replace("\u2013", "-")
        .replace("\u2014", "-")
        .replace("\xa0", " ")
    )
    return cleaned.strip()


def normalize_article_payload(article: Any) -> dict[str, Any] | None:
    """Normalize mixed top_articles payloads (id list or dict) for templates."""
    if not isinstance(article, dict):
        return None

    title = article.get("title")
    url = article.get("url")
    if not title or not url:
        return None

    return {
        "title": title,
        "url": url,
        "engagement_score": article.get("engagement_score"),
        "source": article.get("source"),
    }
