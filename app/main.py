"""FastAPI application with server-rendered templates."""

import logging

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.api.routes import auth, email, users
from app.config import settings
from app.services.mention_stats import get_mention_stats_service
from app.services.rate_limit import rate_limit

# Removed get_sentiment_service_hybrid - main app only needs label conversion, not analysis
from app.services.sentiment_analytics import get_sentiment_analytics_service
from app.services.stock_data import stock_service
from app.services.stock_price_cache import ensure_fresh_stock_price
from app.services.velocity import get_velocity_service

logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(
    title="AlexStocks",
    description="Lean MVP for market news analytics",
    version="0.1.0",
)

# Include routers
app.include_router(auth.router)
app.include_router(users.router)
app.include_router(email.router)

# Setup templates
templates = Jinja2Templates(directory="app/templates")
# Expose runtime settings to templates (for GTM/env-gated features)
templates.env.globals["settings"] = settings


# Add custom filter for URL string conversion
def url_string(url_obj) -> str:
    """Convert URL object to string safely for Jinja2 templates."""
    if url_obj is None:
        return ""
    return str(url_obj)


templates.env.filters["url_string"] = url_string

# Mount static files for logo and assets
app.mount("/static", StaticFiles(directory="app/artifacts"), name="static")


# Add sentiment helper functions to template context
def get_sentiment_display_data(sentiment_score: float | None) -> dict:
    """Get sentiment display data for templates."""
    if sentiment_score is None:
        return {
            "label": "Unknown",
            "color": "gray",
            "bg_color": "bg-gray-100",
            "text_color": "text-gray-800",
            "icon": "❓",
        }

    # Simple threshold-based label conversion (no ML needed - scores already computed by jobs)
    if sentiment_score >= 0.1:
        label = "Positive"
    elif sentiment_score <= -0.1:
        label = "Negative"
    else:
        label = "Neutral"

    if label == "Positive":
        return {
            "label": "Positive",
            "color": "green",
            "bg_color": "bg-green-100",
            "text_color": "text-green-800",
            "icon": "📈",
        }
    elif label == "Negative":
        return {
            "label": "Negative",
            "color": "red",
            "bg_color": "bg-red-100",
            "text_color": "text-red-800",
            "icon": "📉",
        }
    else:
        return {
            "label": "Neutral",
            "color": "gray",
            "bg_color": "bg-gray-100",
            "text_color": "text-gray-800",
            "icon": "➡️",
        }


# Add helper functions to template context
templates.env.globals["get_sentiment_display_data"] = get_sentiment_display_data


def get_velocity_display_data_wrapper(session, ticker: str) -> dict:
    """Wrapper for velocity display data for templates."""
    velocity_service = get_velocity_service(session)
    velocity_data = velocity_service.calculate_velocity(ticker)
    return velocity_service.get_velocity_display_data(velocity_data)


templates.env.globals["get_velocity_display_data"] = get_velocity_display_data_wrapper


def get_sentiment_over_time_data(db, ticker: str, days: int = 30) -> dict:
    """Get sentiment data aggregated over time for bar chart visualization."""
    from datetime import datetime, timedelta

    from sqlalchemy import func

    from app.db.models import Article, ArticleTicker

    try:
        # Clamp days to configured maximum as a defense-in-depth
        days = min(days, settings.MAX_DAYS_TIME_SERIES)
        # Get sentiment data grouped by day for the last N days
        cutoff_date = datetime.utcnow() - timedelta(days=days)

        # Query to get daily positive and negative counts
        from sqlalchemy import case

        daily_sentiment = (
            db.query(
                func.date(Article.published_at).label("date"),
                func.sum(case((Article.sentiment > 0.05, 1), else_=0)).label(
                    "positive_count"
                ),
                func.sum(case((Article.sentiment < -0.05, 1), else_=0)).label(
                    "negative_count"
                ),
            )
            .join(ArticleTicker, Article.id == ArticleTicker.article_id)
            .filter(
                ArticleTicker.ticker == ticker.upper(),
                Article.published_at >= cutoff_date,
                Article.sentiment.isnot(None),
            )
            .group_by(func.date(Article.published_at))
            .order_by(func.date(Article.published_at))
            .all()
        )

        # Create a dictionary for quick lookup
        sentiment_by_date = {}
        for row in daily_sentiment:
            sentiment_by_date[row.date] = {
                "positive": int(row.positive_count or 0),
                "negative": int(row.negative_count or 0),
            }

        # Generate data for all days in the range, filling missing days with zeros
        chart_data = []
        start_date = (datetime.utcnow() - timedelta(days=days)).date()
        end_date = datetime.utcnow().date()

        current_date = start_date
        while current_date <= end_date:
            date_str = current_date.strftime("%Y-%m-%d")
            if current_date in sentiment_by_date:
                chart_data.append(
                    {
                        "date": date_str,
                        "positive": sentiment_by_date[current_date]["positive"],
                        "negative": sentiment_by_date[current_date]["negative"],
                    }
                )
            else:
                chart_data.append({"date": date_str, "positive": 0, "negative": 0})
            current_date += timedelta(days=1)

        return {
            "data": chart_data,
            "period_days": days,
            "total_points": len(chart_data),
        }

    except Exception as e:
        logger.error(f"Error getting sentiment over time data: {e}")
        return {"data": [], "period_days": days, "total_points": 0}


# Mount static files (if needed later)
# app.mount("/static", StaticFiles(directory="app/static"), name="static")


@app.get("/health")
async def health() -> dict[str, bool]:
    """Health check endpoint."""
    return {"ok": True}


@app.get("/robots.txt")
async def robots_txt():
    """Serve robots.txt file."""
    return FileResponse("app/artifacts/robots.txt", media_type="text/plain")


@app.get("/manifest.json")
async def manifest():
    """Serve web manifest file."""
    return FileResponse(
        "app/artifacts/manifest.json", media_type="application/manifest+json"
    )


@app.get("/about", response_class=HTMLResponse)
async def about(request: Request):
    """About page."""
    return templates.TemplateResponse("about.html", {"request": request})


@app.get("/privacy", response_class=HTMLResponse)
async def privacy(request: Request):
    """Privacy policy page."""
    return templates.TemplateResponse("privacy.html", {"request": request})


@app.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request):
    """Settings page for user profile and preferences."""
    return templates.TemplateResponse("settings.html", {"request": request})


@app.get("/api/scraping-status")
async def get_scraping_status():
    """Get the current scraping status for all sources."""
    from app.db.models import ScrapingStatus
    from app.db.session import SessionLocal

    try:
        db = SessionLocal()
        try:
            statuses = db.query(ScrapingStatus).all()

            result = {}
            for status in statuses:
                result[status.source] = {
                    "last_scrape_at": status.last_scrape_at.isoformat(),
                    "items_scraped": status.items_scraped,
                    "status": status.status,
                    "error_message": status.error_message,
                    "updated_at": status.updated_at.isoformat(),
                }

            return result
        finally:
            db.close()
    except Exception as e:
        logger.error(f"Error in scraping status API: {e}")
        return JSONResponse(status_code=500, content={"error": "Internal server error"})


@app.get("/api/stock/{symbol}")
async def get_stock_data(symbol: str):
    """Get current stock price data for a symbol."""
    try:
        stock_data = await stock_service.get_stock_price(symbol.upper())
        if stock_data:
            return stock_data
        else:
            return JSONResponse(
                status_code=404, content={"error": f"Stock data not found for {symbol}"}
            )
    except Exception as e:
        logger.error(f"Error in stock API: {e}")
        return JSONResponse(status_code=500, content={"error": "Internal server error"})


@app.get("/api/sentiment/histogram")
async def get_sentiment_histogram(ticker: str | None = None):
    """Get sentiment histogram data for all articles or a specific ticker."""
    from app.db.session import SessionLocal

    try:
        db = SessionLocal()
        try:
            sentiment_analytics = get_sentiment_analytics_service()
            if ticker:
                sentiment_data = sentiment_analytics.get_sentiment_distribution_data(
                    db, ticker.upper()
                )
            else:
                sentiment_data = sentiment_analytics.get_sentiment_distribution_data(db)

            return sentiment_data
        finally:
            db.close()
    except Exception as e:
        logger.error(f"Error in sentiment histogram API: {e}")
        return JSONResponse(status_code=500, content={"error": "Internal server error"})


@app.get("/api/sentiment/time-series")
async def get_sentiment_time_series(
    ticker: str,
    days: int = Query(30, ge=1, le=settings.MAX_DAYS_TIME_SERIES),
    _: None = Depends(
        rate_limit("sentiment_time_series", requests=60, window_seconds=60)
    ),
):
    """Get sentiment data over time for a specific ticker."""
    from app.db.session import SessionLocal

    try:
        db = SessionLocal()
        try:
            sentiment_data = get_sentiment_over_time_data(db, ticker.upper(), days)
            return sentiment_data
        finally:
            db.close()
    except Exception as e:
        logger.error(f"Error in sentiment time series API: {e}")
        return JSONResponse(status_code=500, content={"error": "Internal server error"})


@app.get("/api/ticker/{ticker}/sentiment-timeline")
async def get_ticker_sentiment_timeline(
    ticker: str,
    period: str = Query("month", regex="^(day|week|month)$"),
    metric: str = Query("comments", regex="^(comments|users)$"),
    _: None = Depends(rate_limit("sentiment_timeline", requests=60, window_seconds=60)),
):
    """Get sentiment timeline data with different time granularities.

    Args:
        ticker: Ticker symbol
        period: Time period - "day" (hourly, 24h), "week" (daily, 7d), or "month" (daily, 30d)
        metric: Metric type - "comments" (count all comments) or "users" (count unique users)

    Returns:
        Timeline data with positive, negative, neutral, and total counts per time bucket
    """
    from datetime import UTC, datetime, timedelta

    from sqlalchemy import case, func

    from app.db.models import Article, ArticleTicker
    from app.db.session import SessionLocal

    try:
        db = SessionLocal()
        try:
            # Define sentiment thresholds
            positive_threshold = 0.05
            negative_threshold = -0.05

            # Determine time range and grouping
            if period == "day":
                hours_back = 24
                cutoff_date = datetime.now(UTC) - timedelta(hours=hours_back)
                # Group by hour
                time_bucket = func.date_trunc("hour", Article.published_at)
            elif period == "week":
                days_back = 7
                cutoff_date = datetime.now(UTC) - timedelta(days=days_back)
                # Group by day
                time_bucket = func.date(Article.published_at)
            else:  # month
                days_back = 30
                cutoff_date = datetime.now(UTC) - timedelta(days=days_back)
                # Group by day
                time_bucket = func.date(Article.published_at)

            # Query based on metric type
            if metric == "comments":
                # Count all comments with sentiment
                timeline_data = (
                    db.query(
                        time_bucket.label("time_bucket"),
                        func.sum(
                            case((Article.sentiment >= positive_threshold, 1), else_=0)
                        ).label("positive"),
                        func.sum(
                            case((Article.sentiment <= negative_threshold, 1), else_=0)
                        ).label("negative"),
                        func.sum(
                            case(
                                (
                                    (Article.sentiment > negative_threshold)
                                    & (Article.sentiment < positive_threshold),
                                    1,
                                ),
                                else_=0,
                            )
                        ).label("neutral"),
                        func.count(Article.id).label("total"),
                    )
                    .join(ArticleTicker, Article.id == ArticleTicker.article_id)
                    .filter(
                        ArticleTicker.ticker == ticker.upper(),
                        Article.published_at >= cutoff_date,
                        Article.sentiment.isnot(None),
                    )
                    .group_by(time_bucket)
                    .order_by(time_bucket)
                    .all()
                )

                # Create a dictionary for quick lookup
                data_by_time = {}
                for row in timeline_data:
                    data_by_time[row.time_bucket] = {
                        "positive": int(row.positive or 0),
                        "negative": int(row.negative or 0),
                        "neutral": int(row.neutral or 0),
                        "total": int(row.total or 0),
                    }
            else:  # metric == "users"
                # Get all articles with time bucket and author
                # We'll process in Python to get latest sentiment per user per bucket
                articles_data = (
                    db.query(
                        time_bucket.label("time_bucket"),
                        Article.author,
                        Article.sentiment,
                        Article.published_at,
                    )
                    .join(ArticleTicker, Article.id == ArticleTicker.article_id)
                    .filter(
                        ArticleTicker.ticker == ticker.upper(),
                        Article.published_at >= cutoff_date,
                        Article.sentiment.isnot(None),
                        Article.author.isnot(None),
                        Article.author != "",
                    )
                    .order_by(time_bucket, Article.published_at.desc())
                    .all()
                )

                # Group by time bucket and author, keeping only latest sentiment
                from collections import defaultdict
                from typing import Any

                user_latest_sentiment: defaultdict[Any, dict[str, float]] = defaultdict(
                    dict
                )

                for row in articles_data:
                    bucket = row.time_bucket
                    author = row.author
                    # Only keep the first (latest) sentiment for each user in each bucket
                    if author not in user_latest_sentiment[bucket]:
                        user_latest_sentiment[bucket][author] = row.sentiment

                # Count sentiment categories per time bucket
                data_by_time = {}
                for bucket, users in user_latest_sentiment.items():
                    positive = sum(1 for s in users.values() if s >= positive_threshold)
                    negative = sum(1 for s in users.values() if s <= negative_threshold)
                    neutral = sum(
                        1
                        for s in users.values()
                        if negative_threshold < s < positive_threshold
                    )
                    total = len(users)

                    data_by_time[bucket] = {
                        "positive": positive,
                        "negative": negative,
                        "neutral": neutral,
                        "total": total,
                    }

            # Fill missing time buckets with zeros for continuous display
            result_data = []
            if period == "day":
                # Generate hourly buckets for last 24 hours
                current_time = datetime.now(UTC).replace(
                    minute=0, second=0, microsecond=0
                )
                for i in range(24):
                    bucket_time = current_time - timedelta(hours=(23 - i))
                    # Try to find the matching bucket in data_by_time
                    # The key might be a datetime or could have slight timezone differences
                    data_point = None
                    for key in data_by_time.keys():
                        # Compare by converting both to naive UTC
                        key_naive = (
                            key.replace(tzinfo=None) if hasattr(key, "tzinfo") else key
                        )
                        bucket_time_naive = bucket_time.replace(tzinfo=None)
                        if key_naive == bucket_time_naive:
                            data_point = data_by_time[key]
                            break

                    if data_point is None:
                        data_point = {
                            "positive": 0,
                            "negative": 0,
                            "neutral": 0,
                            "total": 0,
                        }

                    result_data.append(
                        {"timestamp": bucket_time.isoformat(), **data_point}
                    )
            else:
                # Generate daily buckets
                days = 7 if period == "week" else 30
                current_date = datetime.now(UTC).date()
                for i in range(days):
                    bucket_date = current_date - timedelta(days=(days - 1 - i))
                    if bucket_date in data_by_time:
                        data_point = data_by_time[bucket_date]
                    else:
                        data_point = {
                            "positive": 0,
                            "negative": 0,
                            "neutral": 0,
                            "total": 0,
                        }

                    result_data.append(
                        {
                            "timestamp": datetime.combine(
                                bucket_date, datetime.min.time(), tzinfo=UTC
                            ).isoformat(),
                            **data_point,
                        }
                    )

            return {
                "ticker": ticker.upper(),
                "period": period,
                "metric": metric,
                "data": result_data,
            }
        finally:
            db.close()
    except Exception as e:
        logger.error(f"Error in sentiment timeline API: {e}")
        return JSONResponse(status_code=500, content={"error": "Internal server error"})


@app.get("/api/mentions/hourly")
async def get_mentions_hourly(
    tickers: str,
    hours: int = Query(24, ge=1, le=settings.MAX_HOURS_MENTIONS),
    _: None = Depends(rate_limit("mentions_hourly", requests=60, window_seconds=60)),
):
    """Get hourly mention counts for one or more tickers for the last N hours.

    Query params:
      - tickers: comma-separated symbols (e.g., AAPL,TSLA,NVDA)
      - hours: trailing hours to include (default 24)
    """
    from app.db.session import SessionLocal

    try:
        db = SessionLocal()
        try:
            symbols = [s.strip() for s in tickers.split(",") if s.strip()]
            service = get_mention_stats_service(db)
            payload = service.get_mentions_hourly(symbols, hours=hours)
            return payload
        finally:
            db.close()
    except Exception as e:
        logger.error(f"Error in mentions hourly API: {e}")
        return JSONResponse(status_code=500, content={"error": "Internal server error"})


@app.get("/api/ticker/{ticker}/articles")
async def get_ticker_articles(
    ticker: str,
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=settings.MAX_LIMIT_ARTICLES),
    _: None = Depends(rate_limit("ticker_articles", requests=60, window_seconds=60)),
):
    """Get paginated articles for a specific ticker."""
    from sqlalchemy import desc, func

    from app.db.models import Article, ArticleTicker, Ticker
    from app.db.session import SessionLocal

    try:
        db = SessionLocal()
        try:
            # Get ticker info
            ticker_obj = (
                db.query(Ticker).filter(Ticker.symbol == ticker.upper()).first()
            )
            if not ticker_obj:
                return JSONResponse(
                    status_code=404, content={"error": f"Ticker {ticker} not found"}
                )

            # Get total article count
            total_count = (
                db.query(func.count(ArticleTicker.article_id))
                .filter(ArticleTicker.ticker == ticker.upper())
                .scalar()
                or 0
            )

            # Calculate pagination with server-side clamps and offset guard
            limit = min(limit, settings.MAX_LIMIT_ARTICLES)
            offset = (page - 1) * limit
            if offset > settings.MAX_OFFSET_ITEMS:
                return JSONResponse(
                    status_code=400,
                    content={
                        "error": "Offset too large",
                        "message": "Requested page exceeds maximum offset.",
                    },
                )
            total_pages = (total_count + limit - 1) // limit

            # Get paginated articles
            articles_query = (
                db.query(Article, ArticleTicker.confidence, ArticleTicker.matched_terms)
                .join(ArticleTicker, Article.id == ArticleTicker.article_id)
                .filter(ArticleTicker.ticker == ticker.upper())
                .order_by(desc(Article.published_at))
                .offset(offset)
                .limit(limit)
            )

            articles_with_confidence = articles_query.all()

            # Format articles
            articles = []
            for article, confidence, matched_terms in articles_with_confidence:
                if article.source == "reddit_comment":
                    title = (
                        article.text[:100] + "..."
                        if len(article.text) > 100
                        else article.text
                    )
                    url = article.reddit_url or article.url
                    author_info = f"u/{article.author}" if article.author else "Unknown"
                    subreddit_info = (
                        f"r/{article.subreddit}" if article.subreddit else ""
                    )
                else:
                    title = article.title
                    url = article.url
                    author_info = ""
                    subreddit_info = ""

                article_dict = {
                    "id": article.id,
                    "title": title,
                    "url": url,
                    "published_at": article.published_at.isoformat(),
                    "source": article.source,
                    "lang": article.lang,
                    "sentiment": article.sentiment or 0.0,
                    "confidence": confidence,
                    "author": author_info,
                    "subreddit": subreddit_info,
                    "matched_terms": matched_terms or [],
                }
                articles.append(article_dict)

            return {
                "ticker": ticker.upper(),
                "ticker_name": ticker_obj.name,
                "articles": articles,
                "pagination": {
                    "page": page,
                    "limit": limit,
                    "total": total_count,
                    "total_pages": total_pages,
                    "has_next": page < total_pages,
                    "has_prev": page > 1,
                },
            }
        finally:
            db.close()
    except Exception as e:
        logger.error(f"Error in ticker articles API: {e}")
        return JSONResponse(status_code=500, content={"error": "Internal server error"})


@app.get("/api/stock/{symbol}/chart")
async def get_stock_chart_data(symbol: str, period: str = "1mo"):
    """Get historical stock data for charting from database, combined with current price."""
    from datetime import datetime, timedelta

    from sqlalchemy import desc

    from app.db.models import StockPrice, StockPriceHistory
    from app.db.session import SessionLocal

    try:
        db = SessionLocal()
        try:
            # Map period to number of days
            period_days = {
                "1d": 1,
                "5d": 5,
                "1mo": 30,
                "3mo": 90,
                "6mo": 180,
                "1y": 365,
                "2y": 730,
                "5y": 1825,
            }
            days = period_days.get(period, 30)

            # Get historical data from database
            cutoff_date = datetime.now() - timedelta(days=days)
            historical_data = (
                db.query(StockPriceHistory)
                .filter(
                    StockPriceHistory.symbol == symbol.upper(),
                    StockPriceHistory.date >= cutoff_date,
                )
                .order_by(desc(StockPriceHistory.date))
                .all()
            )

            # Get current price data
            current_price = (
                db.query(StockPrice).filter(StockPrice.symbol == symbol.upper()).first()
            )

            if historical_data:
                chart_points = []
                for point in reversed(
                    historical_data
                ):  # Reverse to get chronological order
                    chart_points.append(
                        {
                            "date": point.date.strftime("%Y-%m-%d"),
                            "price": point.close_price,
                            "volume": point.volume or 0,
                        }
                    )

                # Add current price as latest point if available and more recent
                if current_price and current_price.updated_at:
                    latest_historical_date = historical_data[0].date.date()
                    today = datetime.now().date()

                    if today >= latest_historical_date:
                        # Remove today's historical data if it exists (replace with current)
                        chart_points = [
                            point
                            for point in chart_points
                            if point["date"] != today.strftime("%Y-%m-%d")
                        ]

                        # Add current price as today's data point
                        chart_points.append(
                            {
                                "date": today.strftime("%Y-%m-%d"),
                                "price": current_price.price,
                                "volume": 0,
                            }
                        )

                chart_data = {
                    "symbol": symbol.upper(),
                    "period": period,
                    "data": chart_points,
                    "meta": {"symbol": symbol.upper(), "source": "database+current"},
                }
                return chart_data
            else:
                # No historical data, try current price or API fallback
                if current_price:
                    today = datetime.now().date()
                    chart_points = [
                        {
                            "date": today.strftime("%Y-%m-%d"),
                            "price": current_price.price,
                            "volume": 0,
                        }
                    ]

                    chart_data = {
                        "symbol": symbol.upper(),
                        "period": period,
                        "data": chart_points,
                        "meta": {"symbol": symbol.upper(), "source": "current_only"},
                    }
                    return chart_data
                else:
                    # No data at all - return 404
                    return JSONResponse(
                        status_code=404,
                        content={
                            "error": f"No chart data found for {symbol}",
                            "message": "Historical data not yet collected for this symbol",
                        },
                    )
        finally:
            db.close()

    except Exception as e:
        logger.error(f"Error in chart API: {e}")
        return JSONResponse(status_code=500, content={"error": "Internal server error"})


@app.get("/", response_class=HTMLResponse)
async def home(request: Request, page: int = 1) -> HTMLResponse:
    """Home page with ticker grid showing top 50 most discussed tickers in last 24h."""
    from datetime import datetime, timedelta

    from sqlalchemy import and_, func, or_

    from app.db.models import Article, ArticleTicker, StockPrice, Ticker
    from app.db.session import SessionLocal

    db = SessionLocal()
    try:
        # Calculate 24 hours ago
        twenty_four_hours_ago = datetime.utcnow() - timedelta(hours=24)

        # Get tickers with article counts from last 24h, average sentiment, and stock prices
        # First, get the top 50 most discussed tickers in last 24h
        top_tickers_subquery = (
            db.query(
                ArticleTicker.ticker,
                func.count(ArticleTicker.article_id).label("recent_article_count"),
            )
            .join(Article, ArticleTicker.article_id == Article.id)
            .join(Ticker, Ticker.symbol == ArticleTicker.ticker)
            .filter(
                Article.published_at >= twenty_four_hours_ago,
                or_(Ticker.name.is_(None), ~Ticker.name.ilike("%ETF%")),
            )
            .group_by(ArticleTicker.ticker)
            .order_by(func.count(ArticleTicker.article_id).desc())
            .limit(50)
            .subquery()
        )

        # Now get full data for these top tickers
        tickers_query = (
            db.query(
                Ticker.symbol,
                Ticker.name,
                func.count(ArticleTicker.article_id).label("article_count"),
                func.avg(Article.sentiment).label("avg_sentiment"),
                top_tickers_subquery.c.recent_article_count,
                StockPrice.price,
                StockPrice.previous_close,
                StockPrice.change,
                StockPrice.change_percent,
                StockPrice.market_state,
                StockPrice.currency,
                StockPrice.exchange,
                StockPrice.updated_at,
            )
            .join(top_tickers_subquery, Ticker.symbol == top_tickers_subquery.c.ticker)
            .outerjoin(
                ArticleTicker,
                and_(
                    Ticker.symbol == ArticleTicker.ticker,
                    ArticleTicker.article_id.in_(
                        db.query(Article.id).filter(
                            Article.published_at >= twenty_four_hours_ago
                        )
                    ),
                ),
            )
            .outerjoin(Article, ArticleTicker.article_id == Article.id)
            .outerjoin(StockPrice, Ticker.symbol == StockPrice.symbol)
            .group_by(
                Ticker.symbol,
                Ticker.name,
                top_tickers_subquery.c.recent_article_count,
                StockPrice.price,
                StockPrice.previous_close,
                StockPrice.change,
                StockPrice.change_percent,
                StockPrice.market_state,
                StockPrice.currency,
                StockPrice.exchange,
                StockPrice.updated_at,
            )
            .order_by(top_tickers_subquery.c.recent_article_count.desc(), Ticker.symbol)
        )

        # Get velocity service for calculating velocity data
        velocity_service = get_velocity_service(db)

        # Get sentiment analytics service for overall sentiment (24h)
        sentiment_analytics = get_sentiment_analytics_service()
        overall_sentiment_data = sentiment_analytics.get_sentiment_distribution_data(
            db, days=1
        )
        overall_lean = sentiment_analytics.get_sentiment_lean_data(db, days=1)

        # Execute the query once and collect all data
        ticker_rows = tickers_query.all()

        # Extract symbols for lean map computation
        top_symbols = [row[0] for row in ticker_rows]
        lean_map = sentiment_analytics.get_ticker_lean_map(db, top_symbols, days=1)

        tickers = []
        default_mention_symbols: list[str] = []
        for row in ticker_rows:
            (
                symbol,
                name,
                article_count,
                avg_sentiment,
                recent_article_count,
                price,
                previous_close,
                change,
                change_percent,
                market_state,
                currency,
                exchange,
                updated_at,
            ) = row

            # Skip ETFs from the homepage display to focus on individual equities
            if name and "ETF" in name.upper():
                continue

            # Calculate velocity for this ticker
            velocity_data = velocity_service.calculate_velocity(symbol)

            # Build stock data from DB
            stock_data = None
            if price is not None:
                stock_data = {
                    "symbol": symbol,
                    "price": price,
                    "previous_close": previous_close,
                    "change": change,
                    "change_percent": change_percent,
                    "market_state": market_state,
                    "currency": currency,
                    "exchange": exchange,
                    "last_updated": updated_at.isoformat() if updated_at else None,
                }

            ticker_dict = {
                "symbol": symbol,
                "name": name,
                "article_count": recent_article_count,  # Use 24h count for display
                "avg_sentiment": avg_sentiment,
                "velocity": velocity_data,
                "stock_data": stock_data,
                "sentiment_lean": lean_map.get(symbol, None),
            }
            tickers.append(ticker_dict)
            if len(default_mention_symbols) < 7:
                default_mention_symbols.append(symbol)

        # Get scraping status
        from app.db.models import ScrapingStatus

        scraping_status = (
            db.query(ScrapingStatus).filter(ScrapingStatus.source == "reddit").first()
        )

        scraping_info = None
        if scraping_status:
            scraping_info = {
                "last_scrape_at": scraping_status.last_scrape_at.isoformat(),
                "items_scraped": scraping_status.items_scraped,
                "status": scraping_status.status,
            }

        # Get user's followed tickers if authenticated
        followed_tickers: list[str] = []
        session_token = request.cookies.get("session_token")
        if session_token:
            try:
                from app.services.auth_service import get_auth_service

                auth_service = get_auth_service()
                user = auth_service.get_current_user(db, session_token)
                if user:
                    from app.repos.user_repo import UserRepository

                    repo = UserRepository(db)
                    follows = repo.get_ticker_follows(user.id)
                    followed_tickers = [f.ticker for f in follows]
            except Exception:
                # If auth fails, just continue without followed tickers
                pass

        return templates.TemplateResponse(
            "home.html",
            {
                "request": request,
                "tickers": tickers,
                "sentiment_histogram": overall_sentiment_data,
                "overall_lean": overall_lean,
                "scraping_status": scraping_info,
                "default_mention_symbols": default_mention_symbols,
                "followed_tickers": followed_tickers,
            },
        )
    finally:
        db.close()


@app.get("/api/tickers")
async def get_all_tickers(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=settings.MAX_LIMIT_TICKERS),
    search: str | None = None,
    sort_by: str = "recent_activity",  # recent_activity, alphabetical, total_articles
    _: None = Depends(rate_limit("tickers_list", requests=60, window_seconds=60)),
):
    """Get paginated list of all tickers with optional search and sorting."""
    from datetime import datetime, timedelta

    from sqlalchemy import func

    from app.db.models import Article, ArticleTicker, StockPrice, Ticker
    from app.db.session import SessionLocal

    db = SessionLocal()
    try:
        # Calculate pagination with clamps and offset guard
        limit = min(limit, settings.MAX_LIMIT_TICKERS)
        offset = (page - 1) * limit
        if offset > settings.MAX_OFFSET_ITEMS:
            return {
                "tickers": [],
                "pagination": {
                    "page": page,
                    "limit": limit,
                    "total": 0,
                    "total_pages": 0,
                    "has_next": False,
                    "has_prev": page > 1,
                },
                "error": "Requested page exceeds maximum offset.",
            }

        # Base query for tickers
        base_query = db.query(
            Ticker.symbol,
            Ticker.name,
            func.count(ArticleTicker.article_id).label("total_article_count"),
            func.avg(Article.sentiment).label("avg_sentiment"),
            StockPrice.price,
            StockPrice.previous_close,
            StockPrice.change,
            StockPrice.change_percent,
            StockPrice.market_state,
            StockPrice.currency,
            StockPrice.exchange,
            StockPrice.updated_at,
        )

        # Add search filter if provided (only search ticker symbols)
        if search:
            search_term = f"%{search.upper()}%"
            base_query = base_query.filter(Ticker.symbol.ilike(search_term))

        # Calculate 24h activity for all queries (for consistent ordering)
        twenty_four_hours_ago = datetime.utcnow() - timedelta(hours=24)
        recent_count = (
            db.query(
                ArticleTicker.ticker,
                func.count(ArticleTicker.article_id).label("recent_count"),
            )
            .join(Article, ArticleTicker.article_id == Article.id)
            .filter(Article.published_at >= twenty_four_hours_ago)
            .group_by(ArticleTicker.ticker)
            .subquery()
        )

        # Complete the query with joins and grouping
        tickers_query = (
            base_query.add_columns(
                func.coalesce(recent_count.c.recent_count, 0).label(
                    "recent_activity_count"
                )
            )
            .outerjoin(ArticleTicker, Ticker.symbol == ArticleTicker.ticker)
            .outerjoin(Article, ArticleTicker.article_id == Article.id)
            .outerjoin(StockPrice, Ticker.symbol == StockPrice.symbol)
            .outerjoin(recent_count, Ticker.symbol == recent_count.c.ticker)
            .group_by(
                Ticker.symbol,
                Ticker.name,
                StockPrice.price,
                StockPrice.previous_close,
                StockPrice.change,
                StockPrice.change_percent,
                StockPrice.market_state,
                StockPrice.currency,
                StockPrice.exchange,
                StockPrice.updated_at,
                recent_count.c.recent_count,
            )
        )

        # Apply sorting
        if sort_by == "recent_activity":
            tickers_query = tickers_query.order_by(
                func.coalesce(recent_count.c.recent_count, 0).desc(), Ticker.symbol
            )
        elif sort_by == "alphabetical":
            tickers_query = tickers_query.order_by(Ticker.symbol)
        elif sort_by == "total_articles":
            tickers_query = tickers_query.order_by(
                func.count(ArticleTicker.article_id).desc(), Ticker.symbol
            )

        # Get total count for pagination
        total_query = db.query(Ticker.symbol)
        if search:
            search_term = f"%{search.upper()}%"
            total_query = total_query.filter(Ticker.symbol.ilike(search_term))
        total_count = total_query.count()

        # Apply pagination
        paginated_tickers = tickers_query.offset(offset).limit(limit).all()

        # Format results
        tickers = []
        for row in paginated_tickers:
            # All queries now have the same structure with recent_activity_count
            (
                symbol,
                name,
                total_article_count,
                avg_sentiment,
                price,
                previous_close,
                change,
                change_percent,
                market_state,
                currency,
                exchange,
                updated_at,
                recent_activity_count,
            ) = row

            # Build stock data from DB
            stock_data = None
            if price is not None:
                stock_data = {
                    "symbol": symbol,
                    "price": price,
                    "previous_close": previous_close,
                    "change": change,
                    "change_percent": change_percent,
                    "market_state": market_state,
                    "currency": currency,
                    "exchange": exchange,
                    "last_updated": updated_at.isoformat() if updated_at else None,
                }

            ticker_dict = {
                "symbol": symbol,
                "name": name,
                "article_count": total_article_count,
                "avg_sentiment": avg_sentiment,
                "stock_data": stock_data,
            }
            tickers.append(ticker_dict)

        return {
            "tickers": tickers,
            "pagination": {
                "page": page,
                "limit": limit,
                "total": total_count,
                "total_pages": (total_count + limit - 1) // limit,
                "has_next": page * limit < total_count,
                "has_prev": page > 1,
            },
        }
    finally:
        db.close()


@app.get("/browse", response_class=HTMLResponse)
async def browse_tickers(
    request: Request,
    page: int = 1,
    search: str | None = None,
    sort_by: str = "recent_activity",
) -> HTMLResponse:
    """Browse all tickers with pagination and search."""

    # Get ticker data via API endpoint logic
    api_data = await get_all_tickers(
        page=page, search=search, sort_by=sort_by, limit=50
    )

    followed_tickers: list[str] = []
    session_token = request.cookies.get("session_token")
    if session_token:
        from app.db.session import SessionLocal

        db = SessionLocal()
        try:
            from app.repos.user_repo import UserRepository
            from app.services.auth_service import get_auth_service

            auth_service = get_auth_service()
            user = auth_service.get_current_user(db, session_token)
            if user:
                repo = UserRepository(db)
                follows = repo.get_ticker_follows(user.id)
                followed_tickers = [f.ticker for f in follows]
        except Exception:
            pass
        finally:
            db.close()

    return templates.TemplateResponse(
        "browse.html",
        {
            "request": request,
            "tickers": api_data["tickers"],
            "pagination": api_data["pagination"],
            "search": search or "",
            "sort_by": sort_by,
            "followed_tickers": followed_tickers,
        },
    )


@app.get("/t/{ticker}", response_class=HTMLResponse)
async def ticker_page(
    request: Request,
    ticker: str,
    page: int = 1,
    sentiment: str | None = Query(default=None),
    source: str | None = None,
    start: str | None = None,  # YYYY-MM-DD
    end: str | None = None,  # YYYY-MM-DD
    _: None = Depends(rate_limit("ticker_page", requests=60, window_seconds=60)),
) -> HTMLResponse:
    """Ticker detail page with articles."""
    from datetime import UTC, datetime, timedelta

    from sqlalchemy import desc, func

    from app.db.models import (
        Article,
        ArticleTicker,
        StockPrice,
        StockPriceHistory,
        Ticker,
    )
    from app.db.session import SessionLocal

    db = SessionLocal()
    try:
        # Get ticker info
        ticker_obj = db.query(Ticker).filter(Ticker.symbol == ticker.upper()).first()

        # Ensure we have a fresh price cached for this symbol
        await ensure_fresh_stock_price(
            db,
            ticker.upper(),
            freshness_minutes=settings.STOCK_PRICE_FRESHNESS_MINUTES,
        )

        # Unfiltered total article count for this ticker (for header metrics)
        unfiltered_total_article_count = (
            db.query(func.count(ArticleTicker.article_id))
            .filter(ArticleTicker.ticker == ticker.upper())
            .scalar()
            or 0
        )

        # Get today's article count
        today = datetime.now().date()
        today_start = datetime.combine(today, datetime.min.time())
        today_article_count = (
            db.query(func.count(ArticleTicker.article_id))
            .join(Article, ArticleTicker.article_id == Article.id)
            .filter(
                ArticleTicker.ticker == ticker.upper(),
                Article.published_at >= today_start,
            )
            .scalar()
            or 0
        )

        # Get yesterday's article count for comparison
        yesterday = today - timedelta(days=1)
        yesterday_start = datetime.combine(yesterday, datetime.min.time())
        yesterday_end = datetime.combine(today, datetime.min.time())
        yesterday_article_count = (
            db.query(func.count(ArticleTicker.article_id))
            .join(Article, ArticleTicker.article_id == Article.id)
            .filter(
                ArticleTicker.ticker == ticker.upper(),
                Article.published_at >= yesterday_start,
                Article.published_at < yesterday_end,
            )
            .scalar()
            or 0
        )

        # Calculate percentage change from yesterday
        if yesterday_article_count > 0:
            article_change_percent = (
                (today_article_count - yesterday_article_count)
                / yesterday_article_count
            ) * 100
        elif today_article_count > 0:
            article_change_percent = 100.0  # 100% increase from 0
        else:
            article_change_percent = 0.0

        # Get unique users talking about this ticker today
        unique_users_today = (
            db.query(func.count(func.distinct(Article.author)))
            .join(ArticleTicker, Article.id == ArticleTicker.article_id)
            .filter(
                ArticleTicker.ticker == ticker.upper(),
                Article.published_at >= today_start,
                Article.author.isnot(None),
                Article.author != "",
            )
            .scalar()
            or 0
        )

        # Get unique users from yesterday for comparison
        unique_users_yesterday = (
            db.query(func.count(func.distinct(Article.author)))
            .join(ArticleTicker, Article.id == ArticleTicker.article_id)
            .filter(
                ArticleTicker.ticker == ticker.upper(),
                Article.published_at >= yesterday_start,
                Article.published_at < yesterday_end,
                Article.author.isnot(None),
                Article.author != "",
            )
            .scalar()
            or 0
        )

        # Calculate user change
        users_change = unique_users_today - unique_users_yesterday
        if unique_users_yesterday > 0:
            users_change_percent = (users_change / unique_users_yesterday) * 100
        elif unique_users_today > 0:
            users_change_percent = 100.0  # 100% increase from 0
        else:
            users_change_percent = 0.0

        # Get stock data from database
        stock_data = None
        stock_price = (
            db.query(
                StockPrice.symbol,
                StockPrice.price,
                StockPrice.previous_close,
                StockPrice.change,
                StockPrice.change_percent,
                StockPrice.market_state,
                StockPrice.currency,
                StockPrice.exchange,
                StockPrice.updated_at,
            )
            .filter(StockPrice.symbol == ticker.upper())
            .first()
        )
        if stock_price is not None:
            stock_data = {
                "symbol": stock_price.symbol,
                "price": stock_price.price,
                "previous_close": stock_price.previous_close,
                "change": stock_price.change,
                "change_percent": stock_price.change_percent,
                "market_state": stock_price.market_state,
                "currency": stock_price.currency,
                "exchange": stock_price.exchange,
                "last_updated": (
                    stock_price.updated_at.isoformat()
                    if stock_price.updated_at
                    else None
                ),
            }

        # Get chart data combining historical data + current price
        chart_data = None
        historical_data = (
            db.query(StockPriceHistory)
            .filter(StockPriceHistory.symbol == ticker.upper())
            .order_by(desc(StockPriceHistory.date))
            .limit(30)
            .all()
        )

        if historical_data:
            chart_points = []
            for point in reversed(
                historical_data
            ):  # Reverse to get chronological order
                chart_points.append(
                    {
                        "date": point.date.strftime("%Y-%m-%d"),
                        "price": point.close_price,
                        "volume": point.volume or 0,
                    }
                )

            # Add current price as latest point if it's more recent than last historical data
            if stock_price and stock_price.updated_at:
                latest_historical_date = historical_data[
                    0
                ].date.date()  # Most recent historical date
                today = datetime.now().date()

                # If current price is from today and newer than latest historical data
                if today >= latest_historical_date:
                    # Remove today's historical data if it exists (we'll replace with current price)
                    chart_points = [
                        point
                        for point in chart_points
                        if point["date"] != today.strftime("%Y-%m-%d")
                    ]

                    # Add current price as today's data point
                    chart_points.append(
                        {
                            "date": today.strftime("%Y-%m-%d"),
                            "price": stock_price.price,
                            "volume": 0,  # Volume not available in current price data
                        }
                    )

            chart_data = {
                "symbol": ticker.upper(),
                "period": "1mo",
                "data": chart_points,
                "meta": {"symbol": ticker.upper(), "source": "database+current"},
            }
        else:
            # No historical data, try to create chart from current price + API fallback
            if stock_price:
                # Start with current price point
                today = datetime.now().date()
                chart_points = [
                    {
                        "date": today.strftime("%Y-%m-%d"),
                        "price": stock_price.price,
                        "volume": 0,
                    }
                ]

                chart_data = {
                    "symbol": ticker.upper(),
                    "period": "1mo",
                    "data": chart_points,
                    "meta": {"symbol": ticker.upper(), "source": "current_only"},
                }
            else:
                # No data at all, try to get chart data for UI (may use mock)
                try:
                    chart_data = await stock_service.get_stock_chart_data(
                        ticker.upper(), "1mo"
                    )
                except Exception as e:
                    logger.error(f"Error getting chart data for UI: {e}")
                    chart_data = None

        if not ticker_obj:
            # Ticker doesn't exist - return 404
            raise HTTPException(status_code=404, detail=f"Ticker {ticker} not found")

        # Pagination settings
        articles_per_page = 50
        offset = (page - 1) * articles_per_page

        # Build filtered base query for this ticker
        filtered_query_base = (
            db.query(Article, ArticleTicker.confidence, ArticleTicker.matched_terms)
            .join(ArticleTicker, Article.id == ArticleTicker.article_id)
            .filter(ArticleTicker.ticker == ticker.upper())
        )

        # Apply server-side filters
        # Sentiment thresholds (aligned with analytics)
        positive_threshold = 0.05
        negative_threshold = -0.05
        # Normalize sentiment from query: allow empty/invalid -> None
        if sentiment is not None:
            sentiment = sentiment.strip().lower()
            if sentiment == "":
                sentiment = None
            elif sentiment not in {"positive", "neutral", "negative"}:
                sentiment = None

        if sentiment:
            if sentiment == "positive":
                filtered_query_base = filtered_query_base.filter(
                    Article.sentiment.isnot(None),
                    Article.sentiment > positive_threshold,
                )
            elif sentiment == "negative":
                filtered_query_base = filtered_query_base.filter(
                    Article.sentiment.isnot(None),
                    Article.sentiment < negative_threshold,
                )
            else:  # neutral
                filtered_query_base = filtered_query_base.filter(
                    Article.sentiment.isnot(None),
                    Article.sentiment >= negative_threshold,
                    Article.sentiment <= positive_threshold,
                )

        if source:
            filtered_query_base = filtered_query_base.filter(Article.source == source)

        # Date range filters (inclusive of start, inclusive of end day)
        if start:
            try:
                start_dt = datetime.fromisoformat(start)
                if start_dt.tzinfo is None:
                    start_dt = start_dt.replace(tzinfo=UTC)
                filtered_query_base = filtered_query_base.filter(
                    Article.published_at >= start_dt
                )
            except Exception:
                logger.warning("invalid_start_date", extra={"value": start})

        if end:
            try:
                end_dt = datetime.fromisoformat(end)
                if end_dt.tzinfo is None:
                    end_dt = end_dt.replace(tzinfo=UTC)
                # Add one day to include the entire end date
                filtered_query_base = filtered_query_base.filter(
                    Article.published_at < (end_dt + timedelta(days=1))
                )
            except Exception:
                logger.warning("invalid_end_date", extra={"value": end})

        # Compute filtered count AFTER filters for proper pagination
        filtered_article_count = filtered_query_base.count()

        # Always order newest first, then paginate
        articles_with_confidence = (
            filtered_query_base.order_by(Article.published_at.desc())
            .offset(offset)
            .limit(articles_per_page)
            .all()
        )

        # Calculate pagination info (based on filtered results)
        total_pages = (
            filtered_article_count + articles_per_page - 1
        ) // articles_per_page
        pagination = {
            "page": page,
            "total_pages": total_pages,
            "has_next": page < total_pages,
            "has_prev": page > 1,
            "total_articles": filtered_article_count,
        }

        # Format articles for template
        articles = []
        for article, confidence, matched_terms in articles_with_confidence:
            # Source-specific shaping
            if article.source in {"reddit_comment", "reddit_post", "reddit"}:
                if article.source == "reddit_comment":
                    title = (
                        article.text[:100] + "..."
                        if len(article.text) > 100
                        else article.text
                    )
                else:
                    title = article.title
                url = article.reddit_url or article.url
                author_info = (
                    f"u/{article.author}"
                    if article.author
                    else ("Unknown" if article.source == "reddit_comment" else "")
                )
                subreddit_info = f"r/{article.subreddit}" if article.subreddit else ""
            else:
                title = article.title
                url = article.url
                author_info = ""
                subreddit_info = ""

            article_dict = {
                "id": article.id,
                "title": title,
                "url": url,
                "published_at": article.published_at,
                "source": article.source,
                "lang": article.lang,
                "sentiment": article.sentiment or 0.0,
                "confidence": confidence,
                "author": author_info,
                "subreddit": subreddit_info,
                "num_comments": article.num_comments or 0,
                "full_text": (
                    article.text
                    if article.source in {"reddit_comment", "reddit_post", "reddit"}
                    else None
                ),
                "matched_terms": matched_terms or [],
                "upvotes": article.upvotes or 0,
            }
            articles.append(article_dict)

        # Build list of distinct sources available for this ticker (for filter dropdown)
        sources_available = [
            row[0]
            for row in db.query(Article.source)
            .join(ArticleTicker, ArticleTicker.article_id == Article.id)
            .filter(ArticleTicker.ticker == ticker.upper())
            .distinct()
            .all()
        ]

        # Get user's followed tickers if authenticated
        is_following = False
        session_token = request.cookies.get("session_token")
        if session_token:
            try:
                from app.services.auth_service import get_auth_service

                auth_service = get_auth_service()
                user = auth_service.get_current_user(db, session_token)
                if user:
                    from app.repos.user_repo import UserRepository

                    repo = UserRepository(db)
                    follow = repo.get_ticker_follow(user.id, ticker.upper())
                    is_following = follow is not None
            except Exception:
                # If auth fails, just continue without follow status
                pass

        return templates.TemplateResponse(
            "ticker.html",
            {
                "request": request,
                "ticker": ticker,
                "ticker_obj": ticker_obj,
                "articles": articles,
                "stock_data": stock_data,
                "chart_data": chart_data,
                "total_article_count": unfiltered_total_article_count,
                "filtered_article_count": filtered_article_count,
                "today_article_count": today_article_count,
                "article_change": today_article_count - yesterday_article_count,
                "article_change_percent": article_change_percent,
                "unique_users_today": unique_users_today,
                "users_change": users_change,
                "users_change_percent": users_change_percent,
                "pagination": pagination,
                "sentiment": sentiment,
                "source": source,
                "start": start,
                "end": end,
                "sources_available": sources_available,
                "is_following": is_following,
            },
        )
    finally:
        db.close()
