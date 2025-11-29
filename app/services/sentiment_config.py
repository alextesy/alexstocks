"""Configuration helpers for wiring up sentiment analysis services.

This module centralizes how the sentiment job chooses between the VADER,
hybrid, and LLM-only analyzers. The goal is to keep the call-sites simple
while still allowing environment or CLI overrides when running in ECS.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Literal, cast

Strategy = Literal["hybrid", "llm", "vader"]


@dataclass(slots=True)
class SentimentConfig:
    """Runtime options that control which analyzer to build."""

    strategy: Strategy = "hybrid"
    llm_model_name: str = "ProsusAI/finbert"
    use_gpu: bool = False
    fallback_to_vader: bool = True
    enable_sarcasm_detection: bool = True
    sarcasm_threshold: float = 0.65
    sarcasm_dampening_factor: float = 0.55
    sarcasm_model_name: str | None = None

    @classmethod
    def from_env(cls) -> SentimentConfig:
        """Load sentiment defaults from environment variables.

        The names align with the previous hybrid sentiment service flags so
        existing deployments keep their behavior without additional changes.
        """

        raw_strategy = os.getenv("SENTIMENT_STRATEGY", "hybrid").lower() or "hybrid"
        strategy = cast(
            Strategy,
            raw_strategy if raw_strategy in {"hybrid", "llm", "vader"} else "hybrid",
        )

        return cls(
            strategy=strategy,
            llm_model_name=os.getenv("SENTIMENT_LLM_MODEL", "ProsusAI/finbert"),
            use_gpu=os.getenv("SENTIMENT_USE_GPU", "false").lower() == "true",
            fallback_to_vader=os.getenv("SENTIMENT_FALLBACK_VADER", "true").lower()
            == "true",
            enable_sarcasm_detection=os.getenv(
                "SENTIMENT_SARCASM_DETECTION", "true"
            ).lower()
            == "true",
            sarcasm_threshold=float(os.getenv("SENTIMENT_SARCASM_THRESHOLD", "0.65")),
            sarcasm_dampening_factor=float(
                os.getenv("SENTIMENT_SARCASM_DAMPENING", "0.55")
            ),
            sarcasm_model_name=os.getenv(
                "SENTIMENT_SARCASM_MODEL", "cardiffnlp/twitter-roberta-base-irony"
            ),
        )
