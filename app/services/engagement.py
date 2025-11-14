"""Utility helpers for engagement score calculations."""

from __future__ import annotations

import math
from typing import Final

DEFAULT_UPVOTE_WEIGHT: Final[float] = 0.7
DEFAULT_COMMENT_WEIGHT: Final[float] = 0.3


def calculate_engagement_score(
    upvotes: int | None,
    num_comments: int | None,
    *,
    upvote_weight: float = DEFAULT_UPVOTE_WEIGHT,
    comment_weight: float = DEFAULT_COMMENT_WEIGHT,
) -> float:
    """Return the weighted engagement score for a piece of content."""
    upvote_count = max(0, int(upvotes or 0))
    comment_count = max(0, int(num_comments or 0))
    score = upvote_weight * math.log1p(upvote_count) + comment_weight * math.log1p(
        comment_count
    )
    return float(score)
