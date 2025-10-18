"""FastAPI application with server-rendered templates."""

import logging

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.config import settings
from app.services.mention_stats import get_mention_stats_service
from app.services.sentiment import get_sentiment_service_hybrid
from app.services.sentiment_analytics import get_sentiment_analytics_service
from app.services.stock_data import stock_service
from app.services.velocity import get_velocity_service

logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(
    title="AlexStocks",
    description="Lean MVP for market news analytics",
    version="0.1.0",
)

# Setup templates
templates = Jinja2Templates(directory="app/templates")
# Expose runtime settings to templates (for GTM/env-gated features)
templates.env.globals["settings"] = settings

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

    sentiment_service = get_sentiment_service_hybrid()
    label = sentiment_service.get_sentiment_label(sentiment_score)

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


@app.get("/about", response_class=HTMLResponse)
async def about(request: Request):
    """About page."""
    return templates.TemplateResponse("about.html", {"request": request})


@app.get("/privacy", response_class=HTMLResponse)
async def privacy(request: Request):
    """Privacy policy page."""
    return templates.TemplateResponse("privacy.html", {"request": request})


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
async def get_sentiment_time_series(ticker: str, days: int = 30):
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


@app.get("/api/mentions/hourly")
async def get_mentions_hourly(tickers: str, hours: int = 24):
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
async def get_ticker_articles(ticker: str, page: int = 1, limit: int = 50):
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

            # Calculate pagination
            offset = (page - 1) * limit
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

    from sqlalchemy import and_, func

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
            .filter(Article.published_at >= twenty_four_hours_ago)
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
            if len(default_mention_symbols) < 10:
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

        return templates.TemplateResponse(
            "home.html",
            {
                "request": request,
                "tickers": tickers,
                "sentiment_histogram": overall_sentiment_data,
                "overall_lean": overall_lean,
                "scraping_status": scraping_info,
                "default_mention_symbols": default_mention_symbols,
            },
        )
    finally:
        db.close()


@app.get("/api/tickers")
async def get_all_tickers(
    page: int = 1,
    limit: int = 50,
    search: str | None = None,
    sort_by: str = "recent_activity",  # recent_activity, alphabetical, total_articles
):
    """Get paginated list of all tickers with optional search and sorting."""
    from datetime import datetime, timedelta

    from sqlalchemy import func

    from app.db.models import Article, ArticleTicker, StockPrice, Ticker
    from app.db.session import SessionLocal

    db = SessionLocal()
    try:
        # Calculate pagination
        offset = (page - 1) * limit

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

    return templates.TemplateResponse(
        "browse.html",
        {
            "request": request,
            "tickers": api_data["tickers"],
            "pagination": api_data["pagination"],
            "search": search or "",
            "sort_by": sort_by,
        },
    )


@app.get("/t/{ticker}", response_class=HTMLResponse)
async def ticker_page(request: Request, ticker: str, page: int = 1) -> HTMLResponse:
    """Ticker detail page with articles."""
    from datetime import datetime

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

        # Get total article count for this ticker
        total_article_count = (
            db.query(func.count(ArticleTicker.article_id))
            .filter(ArticleTicker.ticker == ticker.upper())
            .scalar()
            or 0
        )

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
            # Get sentiment histogram even for unknown tickers
            sentiment_analytics = get_sentiment_analytics_service()
            ticker_sentiment_data = sentiment_analytics.get_sentiment_distribution_data(
                db, ticker.upper()
            )

            # Return 404 or redirect to home
            return templates.TemplateResponse(
                "ticker.html",
                {
                    "request": request,
                    "ticker": ticker,
                    "articles": [],
                    "ticker_obj": None,
                    "stock_data": stock_data,
                    "chart_data": chart_data,
                    "sentiment_histogram": ticker_sentiment_data,
                    "total_article_count": total_article_count,
                    "pagination": {
                        "page": 1,
                        "total_pages": 1,
                        "has_next": False,
                        "has_prev": False,
                    },
                },
            )

        # Pagination settings
        articles_per_page = 50
        offset = (page - 1) * articles_per_page

        # Get articles for this ticker with matched terms (paginated)
        articles_query = (
            db.query(Article, ArticleTicker.confidence, ArticleTicker.matched_terms)
            .join(ArticleTicker, Article.id == ArticleTicker.article_id)
            .filter(ArticleTicker.ticker == ticker.upper())
            .order_by(Article.published_at.desc())
            .offset(offset)
            .limit(articles_per_page)
        )

        articles_with_confidence = articles_query.all()

        # Calculate pagination info
        total_pages = (total_article_count + articles_per_page - 1) // articles_per_page
        pagination = {
            "page": page,
            "total_pages": total_pages,
            "has_next": page < total_pages,
            "has_prev": page > 1,
            "total_articles": total_article_count,
        }

        # Get sentiment histogram for this ticker
        sentiment_analytics = get_sentiment_analytics_service()
        ticker_sentiment_data = sentiment_analytics.get_sentiment_distribution_data(
            db, ticker.upper()
        )

        # Get sentiment over time data for visualization
        sentiment_over_time = get_sentiment_over_time_data(db, ticker.upper())

        # Format articles for template
        articles = []
        for article, confidence, matched_terms in articles_with_confidence:
            # For Reddit comments, use the comment text as title and reddit_url as link
            if article.source == "reddit_comment":
                title = (
                    article.text[:100] + "..."
                    if len(article.text) > 100
                    else article.text
                )
                url = article.reddit_url or article.url
                author_info = f"u/{article.author}" if article.author else "Unknown"
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
                "full_text": (
                    article.text if article.source == "reddit_comment" else None
                ),
                "matched_terms": matched_terms or [],
            }
            articles.append(article_dict)

        return templates.TemplateResponse(
            "ticker.html",
            {
                "request": request,
                "ticker": ticker,
                "ticker_obj": ticker_obj,
                "articles": articles,
                "stock_data": stock_data,
                "chart_data": chart_data,
                "sentiment_histogram": ticker_sentiment_data,
                "sentiment_over_time": sentiment_over_time,
                "total_article_count": total_article_count,
                "pagination": pagination,
            },
        )
    finally:
        db.close()
