"""Data Transfer Objects for API boundaries."""

from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum

from app.db.models import LLMSentimentCategory


class EmailCadence(str, Enum):
    """Email delivery cadence options."""

    DAILY_ONLY = "daily_only"
    WEEKLY_ONLY = "weekly_only"
    BOTH = "both"
    NONE = "none"


@dataclass
class TickerLinkDTO:
    """DTO for ticker linking results."""

    ticker: str
    confidence: float
    matched_terms: list[str]
    reasoning: list[str]

    def __post_init__(self):
        """Validate DTO after initialization."""
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(
                f"Confidence must be between 0.0 and 1.0, got {self.confidence}"
            )

        if not self.ticker:
            raise ValueError("Ticker symbol cannot be empty")

        if not isinstance(self.matched_terms, list):
            raise ValueError("matched_terms must be a list")

        if not isinstance(self.reasoning, list):
            raise ValueError("reasoning must be a list")


@dataclass
class MentionsSeriesDTO:
    """Hourly mentions series for a single ticker."""

    symbol: str
    data: list[int]


@dataclass
class MentionsHourlyResponseDTO:
    """Response DTO for hourly mentions across multiple tickers."""

    labels: list[str]
    series: list[MentionsSeriesDTO]
    hours: int


@dataclass
class UserCreateDTO:
    """DTO for creating a new user."""

    email: str
    auth_provider_id: str | None = None
    auth_provider: str | None = None

    def __post_init__(self):
        """Validate DTO after initialization."""
        if not self.email or "@" not in self.email:
            raise ValueError("Valid email is required")


@dataclass
class UserDTO:
    """DTO for user data."""

    id: int
    email: str
    auth_provider_id: str | None
    auth_provider: str | None
    is_active: bool
    is_deleted: bool
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None


@dataclass
class UserProfileCreateDTO:
    """DTO for creating a user profile."""

    user_id: int
    display_name: str | None = None
    timezone: str = "UTC"
    avatar_url: str | None = None
    bio: str | None = None
    preferences: dict | None = None


@dataclass
class UserProfileDTO:
    """DTO for user profile data."""

    user_id: int
    display_name: str | None
    timezone: str
    avatar_url: str | None
    bio: str | None
    preferences: dict | None
    created_at: datetime
    updated_at: datetime


@dataclass
class UserNotificationChannelCreateDTO:
    """DTO for creating a notification channel."""

    user_id: int
    channel_type: str
    channel_value: str
    is_verified: bool = False
    is_enabled: bool = True
    preferences: dict | None = None

    def __post_init__(self):
        """Validate DTO after initialization."""
        valid_types = ["email", "sms", "push", "webhook"]
        if self.channel_type not in valid_types:
            raise ValueError(f"channel_type must be one of {valid_types}")
        if not self.channel_value:
            raise ValueError("channel_value is required")


@dataclass
class UserNotificationChannelDTO:
    """DTO for notification channel data."""

    id: int
    user_id: int
    channel_type: str
    channel_value: str
    is_verified: bool
    is_enabled: bool
    preferences: dict | None
    email_bounced: bool
    bounced_at: datetime | None
    bounce_type: str | None
    created_at: datetime
    updated_at: datetime


@dataclass
class UserTickerFollowCreateDTO:
    """DTO for creating a ticker follow."""

    user_id: int
    ticker: str
    notify_on_signals: bool = True
    notify_on_price_change: bool = False
    price_change_threshold: float | None = None
    custom_alerts: dict | None = None

    def __post_init__(self):
        """Validate DTO after initialization."""
        if not self.ticker:
            raise ValueError("ticker is required")
        if self.price_change_threshold is not None and self.price_change_threshold <= 0:
            raise ValueError("price_change_threshold must be positive")


@dataclass
class UserTickerFollowDTO:
    """DTO for ticker follow data."""

    id: int
    user_id: int
    ticker: str
    ticker_name: str | None = None  # Ticker full name
    order: int = 0  # Display order in watchlist
    notify_on_signals: bool = True
    notify_on_price_change: bool = False
    price_change_threshold: float | None = None
    custom_alerts: dict | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass
class UserProfileUpdateDTO:
    """DTO for updating user profile."""

    nickname: str | None = None  # display_name alias
    avatar_url: str | None = None  # Optional, not exposed in UI for now
    timezone: str | None = None
    notification_defaults: dict | None = (
        None  # Notification preferences: notify_on_surges, notify_on_most_discussed, notify_on_daily_briefing
    )
    email_cadence: EmailCadence | None = None  # Email delivery cadence preference

    def __post_init__(self) -> None:
        """Validate DTO after initialization."""
        if self.nickname is not None:
            if not isinstance(self.nickname, str):
                raise ValueError("nickname must be a string")
            if len(self.nickname) > 100:
                raise ValueError("nickname must be 100 characters or less")
            if len(self.nickname.strip()) == 0:
                raise ValueError("nickname cannot be empty")
        if self.timezone is not None:
            if not isinstance(self.timezone, str):
                raise ValueError("timezone must be a string")
            if len(self.timezone.strip()) == 0:
                raise ValueError("timezone cannot be empty")
        if self.avatar_url is not None:
            if not isinstance(self.avatar_url, str):
                raise ValueError("avatar_url must be a string")
            if len(self.avatar_url) > 500:
                raise ValueError("avatar_url must be 500 characters or less")
        # email_cadence is validated by the type annotation (EmailCadence | None)


@dataclass
class DailyTickerSummaryUpsertDTO:
    """DTO for creating or updating a daily ticker summary."""

    ticker: str
    summary_date: date
    mention_count: int
    engagement_count: int
    avg_sentiment: float | None = None
    sentiment_stddev: float | None = None
    sentiment_min: float | None = None
    sentiment_max: float | None = None
    top_articles: list[int] | None = None
    llm_summary: str | None = None
    llm_summary_bullets: list[str] | None = None
    llm_sentiment: LLMSentimentCategory | None = None
    llm_model: str | None = None
    llm_version: str | None = None


@dataclass
class DailyTickerSummaryDTO:
    """DTO representing a persisted daily ticker summary."""

    id: int
    ticker: str
    summary_date: date
    mention_count: int
    engagement_count: int
    avg_sentiment: float | None
    sentiment_stddev: float | None
    sentiment_min: float | None
    sentiment_max: float | None
    top_articles: list[int] | None
    llm_summary: str | None
    llm_summary_bullets: list[str] | None
    llm_sentiment: LLMSentimentCategory | None
    llm_model: str | None
    llm_version: str | None
    created_at: datetime
    updated_at: datetime


@dataclass
class UserProfileResponseDTO:
    """DTO for user profile API response including notification defaults."""

    id: int
    email: str
    nickname: str | None  # display_name
    avatar_url: str | None  # Read-only, from OAuth provider
    timezone: str
    notification_defaults: dict  # notify_on_surges, notify_on_most_discussed
    created_at: datetime
    updated_at: datetime


@dataclass
class EmailSendResult:
    """Result of an email send operation."""

    success: bool
    message_id: str | None
    error: str | None
    provider: str


# ============================================================================
# Weekly Digest DTOs
# ============================================================================


@dataclass
class WeeklyTickerAggregate:
    """Aggregated ticker data for weekly digest."""

    ticker: str
    ticker_name: str
    total_mentions: int
    total_engagement: int
    days_with_data: int
    avg_sentiment: float | None
    sentiment_trend: str  # "improving", "stable", "declining"
    sentiment_start: float | None  # First day's sentiment
    sentiment_end: float | None  # Last day's sentiment
    dominant_sentiment: str = "neutral"  # Most common sentiment category
    daily_summaries: list[str] = field(default_factory=list)
    daily_sentiments: list[str] = field(default_factory=list)
    daily_bullets: list[list[str]] = field(default_factory=list)


@dataclass
class TopSignal:
    """Top signal/theme from the week."""

    theme: str
    examples: list[str]
    tickers_involved: list[str]


@dataclass
class SentimentDirection:
    """Sentiment trend analysis."""

    direction: str  # "improving", "stable", "declining"
    evidence: str  # Supporting text
    confidence: float  # 0.0-1.0


@dataclass
class WeeklyTickerSummaryBrief:
    """Brief ticker summary for email."""

    ticker: str
    ticker_name: str
    sentiment_emoji: str  # 🚀, 📈, ➡️, 📉, 💀
    one_liner: str
    mention_count: int


@dataclass
class WeeklyDigestContent:
    """Structured content for weekly digest email."""

    week_start: date
    week_end: date
    user_timezone: str
    generated_at: datetime
    headline: str
    highlights: list[str]
    top_signals: list[TopSignal]
    sentiment_direction: SentimentDirection
    risks_opportunities: list[str]
    next_actions: list[str]
    ticker_summaries: list[WeeklyTickerSummaryBrief]
    days_with_data: int = 0
    total_tickers: int = 0


@dataclass
class WeeklyDigestSendRecordDTO:
    """DTO for weekly digest send record."""

    id: int
    user_id: int
    week_start_date: date
    status: str  # pending, sent, failed, skipped
    ticker_count: int
    days_with_data: int
    message_id: str | None
    error: str | None
    skip_reason: str | None
    created_at: datetime
    sent_at: datetime | None


@dataclass
class EmailCadenceResponse:
    """Response DTO for email cadence preference."""

    email_cadence: EmailCadence
    updated_at: datetime


@dataclass
class WeeklyDigestHistoryResponse:
    """Response DTO for weekly digest history."""

    records: list[WeeklyDigestSendRecordDTO]
    total: int
    limit: int
    offset: int


@dataclass
class UserDeletionResponseDTO:
    """Response DTO for user account deletion."""

    success: bool
    message: str
