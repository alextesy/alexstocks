"""SQLAlchemy models for Market Pulse."""

from datetime import UTC, date, datetime
from enum import Enum

from sqlalchemy import (
    JSON,
    BigInteger,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    desc,
)
from sqlalchemy import (
    Enum as SQLEnum,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.types import TypeDecorator


class LLMSentimentCategory(str, Enum):
    """Enum for LLM sentiment categories."""

    TO_THE_MOON = "🚀 To the Moon"
    BULLISH = "Bullish"
    NEUTRAL = "Neutral"
    BEARISH = "Bearish"
    DOOM = "💀 Doom"


class JSONBCompat(TypeDecorator):
    """A type that uses JSONB for PostgreSQL and JSON for other databases."""

    impl = JSON
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(JSONB())
        else:
            return dialect.type_descriptor(JSON())


class LLMSentimentEnumType(TypeDecorator):
    """Type decorator to ensure enum values are used instead of names."""

    impl = SQLEnum(
        LLMSentimentCategory,
        native_enum=True,
        values_callable=lambda x: [e.value for e in LLMSentimentCategory],
    )
    cache_ok = True

    def process_bind_param(self, value, dialect):
        """Convert enum to its value when binding to database."""
        if value is None:
            return None
        # If it's already an enum object, get its value
        if isinstance(value, LLMSentimentCategory):
            return value.value
        # If it's a string that matches an enum name, convert to value
        if isinstance(value, str):
            try:
                # Try to find enum by name first
                for enum_member in LLMSentimentCategory:
                    if enum_member.name == value:
                        return enum_member.value
                # If not found by name, assume it's already a value
                return value
            except (ValueError, AttributeError):
                return value
        return value

    def process_result_value(self, value, dialect):
        """Convert database value back to enum."""
        if value is None:
            return None
        if isinstance(value, str):
            try:
                return LLMSentimentCategory(value)
            except ValueError:
                # If value doesn't match, try to find by name
                for enum_member in LLMSentimentCategory:
                    if enum_member.name == value:
                        return enum_member
                raise
        return value


class BigIntegerCompat(TypeDecorator):
    """A type that uses BigInteger for PostgreSQL and Integer for SQLite (for autoincrement support)."""

    impl = Integer
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(BigInteger())
        else:
            return dialect.type_descriptor(Integer())


class Base(DeclarativeBase):
    """Base class for all models."""

    pass


class Ticker(Base):
    """Ticker universe with aliases for linking."""

    __tablename__ = "ticker"

    symbol: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    aliases: Mapped[list[str]] = mapped_column(
        JSONBCompat, nullable=False, default=list
    )
    exchange: Mapped[str | None] = mapped_column(String(50), nullable=True)
    sources: Mapped[list[str]] = mapped_column(
        JSONBCompat, nullable=False, default=list
    )
    is_sp500: Mapped[bool] = mapped_column(default=False)
    cik: Mapped[str | None] = mapped_column(
        String(20), nullable=True
    )  # SEC CIK identifier

    # Relationships
    articles: Mapped[list["ArticleTicker"]] = relationship(
        "ArticleTicker", back_populates="ticker_obj", cascade="all, delete-orphan"
    )
    summaries: Mapped[list["DailyTickerSummary"]] = relationship(
        "DailyTickerSummary", back_populates="ticker_obj", cascade="all, delete-orphan"
    )


class Article(Base):
    """Articles from various sources."""

    __tablename__ = "article"

    id: Mapped[int] = mapped_column(
        BigIntegerCompat, primary_key=True, autoincrement=True
    )
    source: Mapped[str] = mapped_column(
        String, nullable=False
    )  # e.g., 'reddit_comment', 'reddit_post', 'news', etc.
    url: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    published_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    text: Mapped[str | None] = mapped_column(Text, nullable=True)
    lang: Mapped[str | None] = mapped_column(String, nullable=True)
    sentiment: Mapped[float | None] = mapped_column(Float, nullable=True)
    # Reddit-specific fields
    reddit_id: Mapped[str | None] = mapped_column(
        String(20), unique=True, nullable=True
    )
    subreddit: Mapped[str | None] = mapped_column(String(50), nullable=True)
    author: Mapped[str | None] = mapped_column(String(50), nullable=True)
    upvotes: Mapped[int | None] = mapped_column(Integer, nullable=True, default=0)
    num_comments: Mapped[int | None] = mapped_column(Integer, nullable=True, default=0)
    reddit_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )

    # Relationships
    tickers: Mapped[list["ArticleTicker"]] = relationship(
        "ArticleTicker", back_populates="article", cascade="all, delete-orphan"
    )


class ArticleTicker(Base):
    """Link articles to tickers with confidence scores."""

    __tablename__ = "article_ticker"

    article_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("article.id", ondelete="CASCADE"), primary_key=True
    )
    ticker: Mapped[str] = mapped_column(
        String, ForeignKey("ticker.symbol"), primary_key=True
    )
    confidence: Mapped[float] = mapped_column(default=1.0)
    matched_terms: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)

    # Relationships
    article: Mapped["Article"] = relationship("Article", back_populates="tickers")
    ticker_obj: Mapped["Ticker"] = relationship("Ticker", back_populates="articles")


class RedditThread(Base):
    """Track Reddit discussion threads and scraping progress."""

    __tablename__ = "reddit_thread"

    reddit_id: Mapped[str] = mapped_column(String(20), primary_key=True)
    subreddit: Mapped[str] = mapped_column(String(50), nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    thread_type: Mapped[str] = mapped_column(
        String(20), nullable=False
    )  # 'daily', 'weekend', 'top_post', 'other'
    url: Mapped[str] = mapped_column(String, nullable=False)
    author: Mapped[str | None] = mapped_column(String(50), nullable=True)
    upvotes: Mapped[int | None] = mapped_column(Integer, nullable=True, default=0)
    total_comments: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    scraped_comments: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_scraped_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
    is_complete: Mapped[bool] = mapped_column(default=False)


class StockPrice(Base):
    """Current stock price data with intraday and market metrics."""

    __tablename__ = "stock_price"

    symbol: Mapped[str] = mapped_column(
        String, ForeignKey("ticker.symbol"), primary_key=True
    )

    # Basic price data
    price: Mapped[float] = mapped_column(Float, nullable=False)
    previous_close: Mapped[float | None] = mapped_column(Float, nullable=True)
    change: Mapped[float | None] = mapped_column(Float, nullable=True)
    change_percent: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Intraday trading data
    open: Mapped[float | None] = mapped_column(Float, nullable=True)
    day_high: Mapped[float | None] = mapped_column(Float, nullable=True)
    day_low: Mapped[float | None] = mapped_column(Float, nullable=True)
    volume: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    # Bid/Ask spread
    bid: Mapped[float | None] = mapped_column(Float, nullable=True)
    ask: Mapped[float | None] = mapped_column(Float, nullable=True)
    bid_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ask_size: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Market metrics
    market_cap: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    shares_outstanding: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    average_volume: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    average_volume_10d: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    # Metadata
    market_state: Mapped[str | None] = mapped_column(
        String(20), nullable=True
    )  # 'OPEN', 'CLOSED', 'REGULAR', etc.
    currency: Mapped[str] = mapped_column(String(10), nullable=False, default="USD")
    exchange: Mapped[str | None] = mapped_column(String(50), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )

    # Relationships
    ticker_obj: Mapped["Ticker"] = relationship("Ticker")


class DailyTickerSummary(Base):
    """Daily aggregated ticker summary generated by LLM."""

    __tablename__ = "daily_ticker_summary"

    id: Mapped[int] = mapped_column(
        BigIntegerCompat, primary_key=True, autoincrement=True
    )
    ticker: Mapped[str] = mapped_column(
        String, ForeignKey("ticker.symbol", ondelete="CASCADE"), nullable=False
    )
    summary_date: Mapped[date] = mapped_column(Date, nullable=False)
    mention_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    engagement_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    avg_sentiment: Mapped[float | None] = mapped_column(Float, nullable=True)
    sentiment_stddev: Mapped[float | None] = mapped_column(Float, nullable=True)
    sentiment_min: Mapped[float | None] = mapped_column(Float, nullable=True)
    sentiment_max: Mapped[float | None] = mapped_column(Float, nullable=True)
    top_articles: Mapped[list[dict] | None] = mapped_column(JSONBCompat, nullable=True)
    llm_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    llm_summary_bullets: Mapped[list[str] | None] = mapped_column(
        JSONBCompat, nullable=True
    )
    llm_sentiment: Mapped[LLMSentimentCategory | None] = mapped_column(
        LLMSentimentEnumType(), nullable=True
    )
    llm_model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    llm_version: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    ticker_obj: Mapped["Ticker"] = relationship("Ticker", back_populates="summaries")

    __table_args__ = (
        UniqueConstraint("ticker", "summary_date", name="uq_daily_ticker_summary"),
        Index(
            "ix_daily_ticker_summary_ticker_summary_date_desc",
            "ticker",
            desc("summary_date"),
        ),
    )


class StockPriceHistory(Base):
    """Historical stock price data for charting."""

    __tablename__ = "stock_price_history"

    id: Mapped[int] = mapped_column(
        BigIntegerCompat, primary_key=True, autoincrement=True
    )
    symbol: Mapped[str] = mapped_column(
        String, ForeignKey("ticker.symbol"), nullable=False
    )
    date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    open_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    high_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    low_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    close_price: Mapped[float] = mapped_column(Float, nullable=False)
    volume: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )

    # Relationships
    ticker_obj: Mapped["Ticker"] = relationship("Ticker")


class StockDataCollection(Base):
    """Track stock data collection runs."""

    __tablename__ = "stock_data_collection"

    id: Mapped[int] = mapped_column(
        BigIntegerCompat, primary_key=True, autoincrement=True
    )
    collection_type: Mapped[str] = mapped_column(
        String(20), nullable=False
    )  # 'current', 'historical'
    symbols_requested: Mapped[int] = mapped_column(Integer, nullable=False)
    symbols_success: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    symbols_failed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    errors: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)


class ScrapingStatus(Base):
    """Track scraping status for different sources."""

    __tablename__ = "scraping_status"

    source: Mapped[str] = mapped_column(
        String(50), primary_key=True
    )  # e.g., 'reddit', 'news', etc.
    last_scrape_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    items_scraped: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="success"
    )  # 'success', 'error', 'running'
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )


class User(Base):
    """Core user table with authentication and soft-delete support."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(
        BigIntegerCompat, primary_key=True, autoincrement=True
    )
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    auth_provider_id: Mapped[str | None] = mapped_column(
        String(255), unique=True, nullable=True
    )  # OAuth provider ID (e.g., Google sub)
    auth_provider: Mapped[str | None] = mapped_column(
        String(50), nullable=True
    )  # e.g., 'google', 'github'
    is_active: Mapped[bool] = mapped_column(default=True)
    is_deleted: Mapped[bool] = mapped_column(default=False)  # Soft delete
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Relationships
    profile: Mapped["UserProfile"] = relationship(
        "UserProfile",
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan",
    )
    notification_channels: Mapped[list["UserNotificationChannel"]] = relationship(
        "UserNotificationChannel", back_populates="user", cascade="all, delete-orphan"
    )
    ticker_follows: Mapped[list["UserTickerFollow"]] = relationship(
        "UserTickerFollow", back_populates="user", cascade="all, delete-orphan"
    )


class UserProfile(Base):
    """Extended user profile information."""

    __tablename__ = "user_profiles"

    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    display_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    timezone: Mapped[str] = mapped_column(String(50), nullable=False, default="UTC")
    avatar_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    bio: Mapped[str | None] = mapped_column(Text, nullable=True)
    preferences: Mapped[dict | None] = mapped_column(
        JSONBCompat, nullable=True
    )  # Flexible JSON field for user preferences
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="profile")


class UserNotificationChannel(Base):
    """User notification channel preferences."""

    __tablename__ = "user_notification_channels"

    id: Mapped[int] = mapped_column(
        BigIntegerCompat, primary_key=True, autoincrement=True
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    channel_type: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # 'email', 'sms', 'push', 'webhook'
    channel_value: Mapped[str] = mapped_column(
        String(500), nullable=False
    )  # email address, phone number, device token, webhook URL
    is_verified: Mapped[bool] = mapped_column(default=False)
    is_enabled: Mapped[bool] = mapped_column(default=True)
    preferences: Mapped[dict | None] = mapped_column(
        JSONBCompat, nullable=True
    )  # Channel-specific settings
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="notification_channels")


class UserTickerFollow(Base):
    """Track which tickers a user follows with notification preferences."""

    __tablename__ = "user_ticker_follows"

    id: Mapped[int] = mapped_column(
        BigIntegerCompat, primary_key=True, autoincrement=True
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    ticker: Mapped[str] = mapped_column(
        String, ForeignKey("ticker.symbol"), nullable=False
    )
    notify_on_signals: Mapped[bool] = mapped_column(
        default=True
    )  # Notify on new signals
    notify_on_price_change: Mapped[bool] = mapped_column(
        default=False
    )  # Notify on significant price changes
    price_change_threshold: Mapped[float | None] = mapped_column(
        Float, nullable=True
    )  # Percentage threshold for price alerts
    custom_alerts: Mapped[dict | None] = mapped_column(
        JSONBCompat, nullable=True
    )  # Custom alert conditions
    order: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )  # Display order in watchlist (lower = higher priority)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="ticker_follows")
    ticker_obj: Mapped["Ticker"] = relationship("Ticker")


# Indexes for performance
Index("article_published_at_idx", Article.published_at.desc())
Index("article_ticker_ticker_idx", ArticleTicker.ticker)
# Ticker indexes
Index("ticker_exchange_idx", Ticker.exchange)
Index("ticker_is_sp500_idx", Ticker.is_sp500)
Index("ticker_cik_idx", Ticker.cik)
# Reddit-specific indexes
Index("article_reddit_id_idx", Article.reddit_id)
Index("article_subreddit_idx", Article.subreddit)
Index("article_upvotes_idx", Article.upvotes.desc())
# RedditThread indexes
Index("reddit_thread_subreddit_idx", RedditThread.subreddit)
Index("reddit_thread_type_idx", RedditThread.thread_type)
Index("reddit_thread_last_scraped_idx", RedditThread.last_scraped_at.desc())
Index("reddit_thread_created_idx", RedditThread.created_at.desc())
# Stock price indexes
Index("stock_price_updated_at_idx", StockPrice.updated_at.desc())
Index(
    "stock_price_history_symbol_date_idx",
    StockPriceHistory.symbol,
    StockPriceHistory.date.desc(),
)
Index("stock_price_history_date_idx", StockPriceHistory.date.desc())
Index("stock_data_collection_started_idx", StockDataCollection.started_at.desc())
Index("stock_data_collection_type_idx", StockDataCollection.collection_type)
# User indexes
Index("user_email_idx", User.email)
Index("user_auth_provider_id_idx", User.auth_provider_id)
Index("user_is_deleted_idx", User.is_deleted)
Index("user_created_at_idx", User.created_at.desc())
# UserNotificationChannel indexes
Index("user_notification_channel_user_idx", UserNotificationChannel.user_id)
Index("user_notification_channel_type_idx", UserNotificationChannel.channel_type)
# UserTickerFollow indexes
Index("user_ticker_follow_user_idx", UserTickerFollow.user_id)
Index("user_ticker_follow_ticker_idx", UserTickerFollow.ticker)
Index(
    "user_ticker_follow_user_ticker_idx",
    UserTickerFollow.user_id,
    UserTickerFollow.ticker,
    unique=True,
)
