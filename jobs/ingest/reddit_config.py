"""Configuration loader for Reddit scraper with YAML support."""

import logging
from dataclasses import dataclass, field
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)


@dataclass
class SubredditLimits:
    """Comment and post limits for a subreddit."""

    daily_discussion_max_comments: int | None
    regular_post_max_comments: int | None
    max_top_posts_per_run: int

    @staticmethod
    def from_dict(data: dict) -> "SubredditLimits":
        """Create from dictionary, converting -1 to None (unlimited)."""
        return SubredditLimits(
            daily_discussion_max_comments=_parse_limit(
                data.get("daily_discussion_max_comments", 1000)
            ),
            regular_post_max_comments=_parse_limit(
                data.get("regular_post_max_comments", 100)
            ),
            max_top_posts_per_run=data.get("max_top_posts_per_run", 100),
        )


@dataclass
class SubredditConfig:
    """Configuration for a single subreddit."""

    name: str
    enabled: bool
    daily_discussion_keywords: list[str]
    limits: SubredditLimits

    @staticmethod
    def from_dict(data: dict) -> "SubredditConfig":
        """Create SubredditConfig from dictionary."""
        return SubredditConfig(
            name=data["name"],
            enabled=data.get("enabled", True),
            daily_discussion_keywords=data.get("daily_discussion_keywords", []),
            limits=SubredditLimits.from_dict(data.get("limits", {})),
        )

    def is_daily_discussion(self, title: str) -> bool:
        """Check if a thread title matches daily discussion keywords."""
        title_lower = title.lower()
        return any(
            keyword.lower() in title_lower for keyword in self.daily_discussion_keywords
        )


@dataclass
class RateLimitingConfig:
    """Rate limiting configuration."""

    requests_per_minute: int = 60


@dataclass
class ScrapingConfig:
    """General scraping configuration."""

    batch_save_interval: int = 200
    max_workers: int = 5


@dataclass
class RedditScraperConfig:
    """Complete Reddit scraper configuration."""

    rate_limiting: RateLimitingConfig
    scraping: ScrapingConfig
    subreddits: list[SubredditConfig] = field(default_factory=list)

    @staticmethod
    def from_dict(data: dict) -> "RedditScraperConfig":
        """Create RedditScraperConfig from dictionary."""
        rate_limiting_data = data.get("rate_limiting", {})
        scraping_data = data.get("scraping", {})
        subreddits_data = data.get("subreddits", [])

        return RedditScraperConfig(
            rate_limiting=RateLimitingConfig(
                requests_per_minute=rate_limiting_data.get("requests_per_minute", 60)
            ),
            scraping=ScrapingConfig(
                batch_save_interval=scraping_data.get("batch_save_interval", 200),
                max_workers=scraping_data.get("max_workers", 5),
            ),
            subreddits=[SubredditConfig.from_dict(sub) for sub in subreddits_data],
        )

    def get_enabled_subreddits(self) -> list[SubredditConfig]:
        """Get list of enabled subreddits."""
        return [sub for sub in self.subreddits if sub.enabled]

    def get_subreddit_config(self, subreddit_name: str) -> SubredditConfig | None:
        """Get configuration for a specific subreddit."""
        for sub in self.subreddits:
            if sub.name.lower() == subreddit_name.lower():
                return sub
        return None


def _parse_limit(value: int | None) -> int | None:
    """
    Parse comment limit value.

    Args:
        value: Limit value from config (-1, null, or positive int)

    Returns:
        None for unlimited, positive int otherwise
    """
    if value is None or value == -1:
        return None
    return value


def load_config(config_path: str | Path) -> RedditScraperConfig:
    """
    Load Reddit scraper configuration from YAML file.

    Args:
        config_path: Path to YAML config file

    Returns:
        RedditScraperConfig instance

    Raises:
        FileNotFoundError: If config file doesn't exist
        ValueError: If config is invalid
    """
    config_path = Path(config_path)

    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    try:
        with open(config_path) as f:
            data = yaml.safe_load(f)

        if not data:
            raise ValueError("Config file is empty")

        config = RedditScraperConfig.from_dict(data)

        # Validation
        if not config.subreddits:
            logger.warning("No subreddits configured")

        enabled = config.get_enabled_subreddits()
        if not enabled:
            logger.warning("No enabled subreddits in configuration")
        else:
            logger.info(
                f"Loaded config: {len(enabled)} enabled subreddit(s): "
                f"{', '.join(sub.name for sub in enabled)}"
            )

        return config

    except yaml.YAMLError as e:
        raise ValueError(f"Invalid YAML in config file: {e}") from e
    except KeyError as e:
        raise ValueError(f"Missing required config field: {e}") from e
    except Exception as e:
        raise ValueError(f"Error loading config: {e}") from e


def get_default_config_path() -> Path:
    """Get default config file path."""
    # Assume we're running from /app when in Docker, or from repo root locally
    candidates = [
        Path("config/reddit_scraper_config.yaml"),  # Docker path
        Path("jobs/config/reddit_scraper_config.yaml"),  # Local from repo root
        Path(__file__).parent.parent
        / "config"
        / "reddit_scraper_config.yaml",  # Relative
    ]

    for path in candidates:
        if path.exists():
            return path

    # Return first candidate as default even if it doesn't exist
    return candidates[0]
