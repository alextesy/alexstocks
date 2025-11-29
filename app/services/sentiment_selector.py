"""Simple factory for picking the right sentiment analyzer.

The goal is to keep job orchestration code focused on scheduling and
database work. This module translates a ``SentimentConfig`` into an object
with an ``analyze_sentiment`` method (either VADER-only, LLM-only, or the
existing hybrid).
"""

from __future__ import annotations

from app.services.hybrid_sentiment import HybridSentimentService
from app.services.sentiment import SentimentService
from app.services.sentiment_config import SentimentConfig


def build_sentiment_service(
    config: SentimentConfig,
) -> HybridSentimentService | SentimentService:
    """Create a sentiment analyzer according to the supplied config."""

    if config.strategy == "vader":
        return SentimentService()

    if config.strategy == "llm":
        return HybridSentimentService(
            use_llm=True,
            llm_model_name=config.llm_model_name,
            use_gpu=config.use_gpu,
            fallback_to_vader=config.fallback_to_vader,
            dual_model_strategy=False,
            enable_sarcasm_detection=config.enable_sarcasm_detection,
            sarcasm_threshold=config.sarcasm_threshold,
            sarcasm_dampening_factor=config.sarcasm_dampening_factor,
            sarcasm_model_name=config.sarcasm_model_name,
        )

    # Default to the richer hybrid mode.
    return HybridSentimentService(
        use_llm=True,
        llm_model_name=config.llm_model_name,
        use_gpu=config.use_gpu,
        fallback_to_vader=config.fallback_to_vader,
        dual_model_strategy=True,
        enable_sarcasm_detection=config.enable_sarcasm_detection,
        sarcasm_threshold=config.sarcasm_threshold,
        sarcasm_dampening_factor=config.sarcasm_dampening_factor,
        sarcasm_model_name=config.sarcasm_model_name,
    )
