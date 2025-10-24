"""Configuration management using pydantic-settings."""

from typing import Literal

from pydantic import AliasChoices, Field, PostgresDsn
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

    model_config = {"env_file": ".env", "extra": "ignore"}


# Global settings instance
settings = Settings()
