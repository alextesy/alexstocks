"""Configuration management using pydantic-settings."""

from typing import Literal

from pydantic import PostgresDsn
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings with environment variable support."""

    postgres_url: PostgresDsn
    tickers_path: str = "data/tickers_core.csv"
    aliases_path: str = "data/aliases.yaml"
    gdelt_concurrency: int = 2
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
    
    # Reddit API configuration
    reddit_client_id: str | None = None
    reddit_client_secret: str | None = None
    reddit_user_agent: str = "MarketPulse/1.0 by MarketPulseBot"
    
    # Finnhub API configuration
    finnhub_secret: str | None = None

    model_config = {"env_file": ".env"}


# Global settings instance
settings = Settings()
