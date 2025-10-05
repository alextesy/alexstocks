"""Stock data service for fetching real-time and historical stock prices using yfinance."""

import asyncio
import logging
import time
from datetime import datetime

import pandas as pd
import yfinance as yf

logger = logging.getLogger(__name__)


class StockDataService:
    """Service for fetching stock price data using Yahoo Finance (yfinance)."""

    def __init__(self):
        self.timeout = 10.0
        self.max_retries = 3
        self.base_delay = 1.0  # Base delay for exponential backoff
        # Track rate limiting
        self._last_request_time = 0.0
        self._min_request_interval = 0.5  # Minimum 500ms between requests

    async def _rate_limit(self):
        """Implement rate limiting between requests."""
        current_time = time.time()
        time_since_last_request = current_time - self._last_request_time

        if time_since_last_request < self._min_request_interval:
            wait_time = self._min_request_interval - time_since_last_request
            await asyncio.sleep(wait_time)

        self._last_request_time = time.time()

    def _normalize_symbol(self, symbol: str) -> str:
        """Normalize symbol for Yahoo Finance format."""
        # Symbol mappings for special cases
        symbol_map = {
            "BRK.B": "BRK-B",
            "BRK.A": "BRK-A",
        }
        return symbol_map.get(symbol.upper(), symbol.upper())

    async def get_stock_price(self, symbol: str) -> dict | None:
        """
        Get current stock price and basic info for a symbol using Yahoo Finance.
        Returns None if data unavailable (no mock data fallback).
        """
        normalized_symbol = self._normalize_symbol(symbol)

        for attempt in range(self.max_retries):
            try:
                await self._rate_limit()

                # Fetch data using yfinance
                data = await self._fetch_from_yahoo(normalized_symbol)
                if data:
                    return data

                # If no data on first attempt, retry with exponential backoff
                if attempt < self.max_retries - 1:
                    delay = self.base_delay * (2**attempt)
                    logger.warning(
                        f"Attempt {attempt + 1} failed for {symbol}, retrying in {delay}s"
                    )
                    await asyncio.sleep(delay)

            except Exception as e:
                logger.error(
                    f"Error fetching {symbol} (attempt {attempt + 1}/{self.max_retries}): {e}"
                )
                if attempt < self.max_retries - 1:
                    delay = self.base_delay * (2**attempt)
                    await asyncio.sleep(delay)

        logger.error(
            f"Failed to fetch data for {symbol} after {self.max_retries} attempts"
        )
        return None

    async def _fetch_from_yahoo(self, symbol: str) -> dict | None:
        """Fetch current price data from Yahoo Finance using yfinance."""
        try:
            # Run yfinance in executor to avoid blocking event loop
            loop = asyncio.get_event_loop()
            ticker = await loop.run_in_executor(None, lambda: yf.Ticker(symbol))

            # Get current info
            info = await loop.run_in_executor(None, lambda: ticker.info)

            if not info or "currentPrice" not in info:
                # Try fast_info as fallback
                try:
                    fast_info = await loop.run_in_executor(
                        None, lambda: ticker.fast_info
                    )
                    if not fast_info or "lastPrice" not in fast_info:
                        logger.warning(f"No price data available for {symbol}")
                        return None

                    last_price = fast_info.get("lastPrice")
                    if last_price is None or last_price == 0:
                        logger.warning(
                            f"No valid price for {symbol} (possibly delisted)"
                        )
                        return None

                    current_price = float(last_price)
                    previous_close = float(
                        fast_info.get("previousClose", current_price)
                    )
                except Exception as e:
                    # Don't retry for clearly invalid tickers (delisted, warrants, etc.)
                    if "delisted" in str(e).lower() or "not found" in str(e).lower():
                        logger.warning(f"Skipping {symbol}: likely delisted or invalid")
                        return None
                    logger.error(f"Error fetching fast_info for {symbol}: {e}")
                    return None
            else:
                current_price = float(info.get("currentPrice", 0))
                previous_close = float(
                    info.get(
                        "previousClose",
                        info.get("regularMarketPreviousClose", current_price),
                    )
                )

            if current_price <= 0:
                logger.warning(f"Invalid price ({current_price}) for {symbol}")
                return None

            # Calculate change
            change = current_price - previous_close
            change_percent = (
                (change / previous_close * 100) if previous_close > 0 else 0
            )

            # Determine market state
            market_state = info.get("marketState", "CLOSED") if info else "CLOSED"

            # Get exchange and currency
            exchange = (
                info.get("exchange", info.get("fullExchangeName", "")) if info else ""
            )
            currency = info.get("currency", "USD") if info else "USD"

            return {
                "symbol": symbol,
                "price": round(current_price, 2),
                "previous_close": round(previous_close, 2),
                "change": round(change, 2),
                "change_percent": round(change_percent, 2),
                "currency": currency,
                "market_state": market_state.upper(),
                "exchange": exchange,
                "last_updated": datetime.now().isoformat(),
            }

        except Exception as e:
            logger.error(f"Yahoo Finance API error for {symbol}: {e}")
            return None

    async def get_stock_chart_data(
        self, symbol: str, period: str = "1mo"
    ) -> dict | None:
        """
        Get historical stock data for charting using Yahoo Finance.
        Returns None if data unavailable (no mock data fallback).
        """
        normalized_symbol = self._normalize_symbol(symbol)

        for attempt in range(self.max_retries):
            try:
                await self._rate_limit()

                data = await self._fetch_historical_yahoo(normalized_symbol, period)
                if data:
                    return data

                # Retry with exponential backoff
                if attempt < self.max_retries - 1:
                    delay = self.base_delay * (2**attempt)
                    logger.warning(
                        f"Historical data attempt {attempt + 1} failed for {symbol}, retrying in {delay}s"
                    )
                    await asyncio.sleep(delay)

            except Exception as e:
                logger.error(
                    f"Error fetching historical data for {symbol} (attempt {attempt + 1}/{self.max_retries}): {e}"
                )
                if attempt < self.max_retries - 1:
                    delay = self.base_delay * (2**attempt)
                    await asyncio.sleep(delay)

        logger.error(
            f"Failed to fetch historical data for {symbol} after {self.max_retries} attempts"
        )
        return None

    async def _fetch_historical_yahoo(self, symbol: str, period: str) -> dict | None:
        """Fetch historical data from Yahoo Finance."""
        try:
            # Map period to yfinance period
            period_map = {
                "1d": "1d",
                "5d": "5d",
                "1mo": "1mo",
                "3mo": "3mo",
                "6mo": "6mo",
                "1y": "1y",
                "2y": "2y",
                "5y": "5y",
            }
            yf_period = period_map.get(period, "1mo")

            # Create ticker object and fetch data
            ticker = yf.Ticker(symbol)

            # Run in executor to avoid blocking the event loop
            loop = asyncio.get_event_loop()
            hist = await loop.run_in_executor(
                None, lambda: ticker.history(period=yf_period)
            )

            if hist.empty:
                logger.warning(f"No historical data from Yahoo Finance for {symbol}")
                return None

            # Convert to our format with OHLCV data
            chart_data = []
            for date, row in hist.iterrows():
                chart_data.append(
                    {
                        "date": date.strftime("%Y-%m-%d"),
                        "open": (
                            round(float(row["Open"]), 2)
                            if "Open" in row and not pd.isna(row["Open"])
                            else None
                        ),
                        "high": (
                            round(float(row["High"]), 2)
                            if "High" in row and not pd.isna(row["High"])
                            else None
                        ),
                        "low": (
                            round(float(row["Low"]), 2)
                            if "Low" in row and not pd.isna(row["Low"])
                            else None
                        ),
                        "close": round(float(row["Close"]), 2),
                        "price": round(
                            float(row["Close"]), 2
                        ),  # For backwards compatibility
                        "volume": (
                            int(row["Volume"])
                            if "Volume" in row and not pd.isna(row["Volume"])
                            else 0
                        ),
                    }
                )

            if not chart_data:
                return None

            return {
                "symbol": symbol,
                "period": period,
                "data": chart_data,
                "meta": {"symbol": symbol, "source": "yahoo"},
            }

        except Exception as e:
            logger.error(f"Yahoo Finance API error for {symbol}: {e}")
            return None

    async def get_multiple_prices(self, symbols: list[str]) -> dict[str, dict | None]:
        """
        Get current prices for multiple symbols.
        Returns dict mapping symbol to price data (or None if unavailable).
        """
        results = {}

        # Process symbols with rate limiting
        for symbol in symbols:
            try:
                data = await self.get_stock_price(symbol)
                results[symbol] = data
            except Exception as e:
                logger.error(f"Error getting price for {symbol}: {e}")
                results[symbol] = None

        return results

    async def get_historical_data(
        self, symbol: str, period: str = "1mo"
    ) -> dict | None:
        """
        Get historical data for a symbol.
        Returns None if data unavailable (no mock data fallback).
        """
        return await self.get_stock_chart_data(symbol, period)


# Create service instance
stock_service = StockDataService()
