"""Data Transfer Objects for API boundaries."""

from dataclasses import dataclass


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
