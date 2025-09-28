"""Velocity calculation service for measuring ticker activity levels."""

import logging
from datetime import datetime, timedelta
from typing import Literal

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import settings
from app.db.models import Article, ArticleTicker

logger = logging.getLogger(__name__)

VelocityLevel = Literal["low", "medium", "high"]


class VelocityService:
    """Service for calculating ticker velocity (activity level)."""
    
    def __init__(self, session: Session):
        self.session = session
    
    def calculate_velocity(self, ticker: str) -> dict:
        """
        Calculate velocity for a ticker.
        
        Velocity = z-score vs baseline (activity level compared to historical average)
        
        Returns:
            dict with recent_count, baseline_avg, velocity_score, and level
        """
        now = datetime.utcnow()
        recent_window = now - timedelta(hours=settings.velocity_window_hours)
        baseline_start = now - timedelta(days=settings.baseline_days)
        
        # Get recent count (last 24h by default)
        recent_count = (
            self.session.query(func.count(Article.id))
            .join(ArticleTicker, Article.id == ArticleTicker.article_id)
            .filter(
                ArticleTicker.ticker == ticker.upper(),
                Article.published_at >= recent_window
            )
            .scalar() or 0
        )
        
        # Get baseline average (daily average over baseline period)
        baseline_total = (
            self.session.query(func.count(Article.id))
            .join(ArticleTicker, Article.id == ArticleTicker.article_id)
            .filter(
                ArticleTicker.ticker == ticker.upper(),
                Article.published_at >= baseline_start,
                Article.published_at < recent_window
            )
            .scalar() or 0
        )
        
        # Calculate daily baseline average
        baseline_days_actual = max(1, settings.baseline_days)
        baseline_avg = baseline_total / baseline_days_actual
        
        # Calculate velocity score (simplified z-score)
        if baseline_avg > 0:
            velocity_score = (recent_count - baseline_avg) / (baseline_avg + 1)  # +1 to avoid division issues
        else:
            velocity_score = 1.0 if recent_count > 0 else 0.0
        
        # Determine velocity level
        level = self._get_velocity_level(recent_count, baseline_avg, velocity_score)
        
        return {
            "recent_count": recent_count,
            "baseline_avg": round(baseline_avg, 2),
            "velocity_score": round(velocity_score, 2),
            "level": level
        }
    
    def _get_velocity_level(self, recent_count: int, baseline_avg: float, velocity_score: float) -> VelocityLevel:
        """Determine velocity level based on counts and score."""
        # High: Significant increase from baseline OR high absolute count
        if recent_count >= 10 or (baseline_avg > 0 and velocity_score > 1.0):
            return "high"
        
        # Medium: Moderate activity or slight increase
        elif recent_count >= 3 or (baseline_avg > 0 and velocity_score > 0.2):
            return "medium"
        
        # Low: Little activity
        else:
            return "low"
    
    def get_velocity_display_data(self, velocity_data: dict) -> dict:
        """Get velocity display data for templates."""
        level = velocity_data["level"]
        recent_count = velocity_data["recent_count"]
        
        if level == "high":
            return {
                "label": f"High ({recent_count} recent)",
                "color": "red",
                "bg_color": "bg-red-100",
                "text_color": "text-red-800",
                "icon": "🔥"
            }
        elif level == "medium":
            return {
                "label": f"Medium ({recent_count} recent)",
                "color": "yellow",
                "bg_color": "bg-yellow-100", 
                "text_color": "text-yellow-800",
                "icon": "📊"
            }
        else:
            return {
                "label": f"Low ({recent_count} recent)",
                "color": "gray",
                "bg_color": "bg-gray-100",
                "text_color": "text-gray-800", 
                "icon": "📉"
            }


def get_velocity_service(session: Session) -> VelocityService:
    """Factory function to get velocity service instance."""
    return VelocityService(session)

