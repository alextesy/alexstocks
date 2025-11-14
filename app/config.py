"""Configuration management using pydantic-settings."""

from typing import Literal, Optional

from pydantic import AliasChoices, Field, PostgresDsn, field_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings with environment variable support."""

    postgres_url: PostgresDsn = Field(
        default="postgresql://test:test@localhost:5432/test",  # type: ignore[assignment]
        validation_alias=AliasChoices("DATABASE_URL", "POSTGRES_URL", "postgres_url"),
    )
    postgres_password: str | None = None  # Allow but don't require
    tickers_path: str = "data/tickers_core.csv"
    aliases_path: str = "data/aliases.yaml"
    rate_limit_per_min: int = 30
    sentiment_provider: Literal["vader"] = "vader"
    velocity_window_hours: int = 24
    baseline_days: int = 7

    # Sentiment Analysis Configuration (LLM by default)
    sentiment_use_llm: bool = True
    sentiment_llm_model: str = "ProsusAI/finbert"
    sentiment_use_gpu: bool = False
    sentiment_fallback_vader: bool = True
    sentiment_dual_model: bool = True
    sentiment_strong_threshold: float = 0.2

    # Sentiment display configuration
    # When neutral share >= this threshold, show Neutral on cards
    sentiment_neutral_dominance_threshold: float = 0.80

    # Reddit API configuration
    reddit_client_id: str | None = None
    reddit_client_secret: str | None = None
    reddit_user_agent: str = "MarketPulse/1.0 by MarketPulseBot"

    # Finnhub API configuration
    finnhub_secret: str | None = None

    # Runtime environment and analytics
    environment: Literal["development", "staging", "production"] = Field(
        default="development",
        validation_alias=AliasChoices("ENV", "environment"),
    )
    gtm_container_id: str | None = Field(
        default=None,
        validation_alias=AliasChoices("GTM_CONTAINER_ID", "gtm_container_id"),
    )
    cookie_consent_enabled: bool = True

    # Redis / Rate limiting configuration
    redis_url: str = Field(
        default="redis://localhost:6379/0",
        validation_alias=AliasChoices("REDIS_URL", "redis_url"),
    )
    # Default budgets are per-IP, per-endpoint
    rl_requests_per_minute: int = 60
    rl_window_seconds: int = 60

    # Parameter caps to protect the API from abuse
    MAX_LIMIT_ARTICLES: int = 100
    MAX_LIMIT_TICKERS: int = 100
    MAX_DAYS_TIME_SERIES: int = 90
    MAX_HOURS_MENTIONS: int = 168
    # Prevent deep scans; applies to (page-1)*limit derived offset
    MAX_OFFSET_ITEMS: int = 5000

    # Stock price cache configuration
    STOCK_PRICE_FRESHNESS_MINUTES: int = 15

    # User limits
    USER_MAX_TICKER_FOLLOWS: int = 100

    # Google OAuth configuration
    google_client_id: str | None = Field(
        default=None,
        validation_alias=AliasChoices("GOOGLE_CLIENT_ID", "google_client_id"),
    )
    google_client_secret: str | None = Field(
        default=None,
        validation_alias=AliasChoices("GOOGLE_CLIENT_SECRET", "google_client_secret"),
    )
    google_redirect_uri: str = Field(
        default="http://localhost:8000/auth/callback",
        validation_alias=AliasChoices("GOOGLE_REDIRECT_URI", "google_redirect_uri"),
    )
    # Session/JWT configuration
    session_secret_key: str = Field(
        default="dev-secret-key-change-in-production",
        validation_alias=AliasChoices("SESSION_SECRET_KEY", "session_secret_key"),
    )
    session_max_age_seconds: int = 86400 * 30  # 30 days

    # Slack configuration
    slack_bot_token: str | None = Field(
        default=None,
        validation_alias=AliasChoices("SLACK_BOT_TOKEN", "slack_bot_token"),
    )
    slack_default_channel: str | None = Field(
        default=None,
        validation_alias=AliasChoices("SLACK_DEFAULT_CHANNEL", "slack_default_channel"),
    )
    slack_users_channel: str | None = Field(
        default=None,
        validation_alias=AliasChoices("SLACK_USERS_CHANNEL", "slack_users_channel"),
    )

    # LLM + Daily summary configuration
    openai_api_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("OPENAI_API_KEY", "openai_api_key"),
    )
    daily_summary_llm_model: str = Field(
        default="gpt-4.1-mini",
        validation_alias=AliasChoices(
            "DAILY_SUMMARY_LLM_MODEL", "daily_summary_llm_model"
        ),
    )
    daily_summary_min_mentions: int = Field(
        default=10,
        ge=1,
        validation_alias=AliasChoices(
            "DAILY_SUMMARY_MIN_MENTIONS", "daily_summary_min_mentions"
        ),
    )
    daily_summary_max_tickers: int = Field(
        default=10,
        ge=1,
        validation_alias=AliasChoices(
            "DAILY_SUMMARY_MAX_TICKERS", "daily_summary_max_tickers"
        ),
    )
    daily_summary_window_timezone: str = Field(
        default="America/New_York",
        validation_alias=AliasChoices(
            "DAILY_SUMMARY_WINDOW_TIMEZONE", "daily_summary_window_timezone"
        ),
    )
    daily_summary_window_start_hour: int = Field(
        default=7,
        ge=0,
        le=23,
        validation_alias=AliasChoices(
            "DAILY_SUMMARY_WINDOW_START_HOUR",
            "daily_summary_window_start_hour",
        ),
    )
    daily_summary_window_end_hour: int = Field(
        default=19,
        ge=0,
        le=23,
        validation_alias=AliasChoices(
            "DAILY_SUMMARY_WINDOW_END_HOUR",
            "daily_summary_window_end_hour",
        ),
    )
    daily_summary_start_offset_minutes: int = Field(
        default=30,
        ge=0,
        validation_alias=AliasChoices(
            "DAILY_SUMMARY_START_OFFSET_MINUTES",
            "daily_summary_start_offset_minutes",
        ),
    )
    daily_summary_end_offset_minutes: int = Field(
        default=90,
        ge=0,
        validation_alias=AliasChoices(
            "DAILY_SUMMARY_END_OFFSET_MINUTES",
            "daily_summary_end_offset_minutes",
        ),
    )
    daily_summary_llm_temperature: float = Field(
        default=0.7,
        ge=0.0,
        le=1.0,
        validation_alias=AliasChoices(
            "DAILY_SUMMARY_LLM_TEMPERATURE", "daily_summary_llm_temperature"
        ),
    )
    daily_summary_llm_timeout_seconds: int = Field(
        default=30,
        ge=1,
        validation_alias=AliasChoices(
            "DAILY_SUMMARY_LLM_TIMEOUT_SECONDS",
            "daily_summary_llm_timeout_seconds",
        ),
    )
    daily_summary_llm_max_tokens: int = Field(
        default=1000,
        ge=1,
        validation_alias=AliasChoices(
            "DAILY_SUMMARY_LLM_MAX_TOKENS", "daily_summary_llm_max_tokens"
        ),
    )

    # Email configuration
    email_provider: Literal["ses", "sendgrid"] = Field(
        default="ses",
        validation_alias=AliasChoices("EMAIL_PROVIDER", "email_provider"),
    )
    email_from_address: str = Field(
        default="noreply@alexstocks.com",
        validation_alias=AliasChoices("EMAIL_FROM_ADDRESS", "email_from_address"),
    )
    email_from_name: str = Field(
        default="AlexStocks",
        validation_alias=AliasChoices("EMAIL_FROM_NAME", "email_from_name"),
    )
    aws_ses_region: str = Field(
        default="us-east-1",
        validation_alias=AliasChoices("AWS_SES_REGION", "aws_ses_region"),
    )

    # Test email configuration
    test_email_recipient: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("TEST_EMAIL_RECIPIENT", "test_email_recipient"),
    )

    @field_validator("test_email_recipient")
    @classmethod
    def validate_test_email_recipient(cls, v):
        if not v:
            raise ValueError("TEST_EMAIL_RECIPIENT must be set in .env file")
        return v

    model_config = {"env_file": ".env", "extra": "ignore"}


# Global settings instance
settings = Settings()
