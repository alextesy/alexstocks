"""Carefully collect real stock prices from Yahoo Finance with proper rate limiting."""

import asyncio
import sys
import logging
from datetime import datetime

sys.path.append('.')

from app.db.session import SessionLocal
from app.db.models import StockPrice, Ticker
from app.services.stock_data import StockDataService

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def collect_real_yahoo_prices():
    """Collect real prices from Yahoo Finance only, with careful rate limiting."""
    
    stock_service = StockDataService()
    db = SessionLocal()
    
    try:
        # Get all ticker symbols
        symbols = [ticker.symbol for ticker in db.query(Ticker).limit(10).all()]  # Start with just 10
        logger.info(f"Collecting real Yahoo Finance prices for {len(symbols)} symbols")
        
        success_count = 0
        failed_count = 0
        
        for i, symbol in enumerate(symbols):
            try:
                logger.info(f"Processing {symbol} ({i+1}/{len(symbols)})...")
                
                # Try Yahoo Finance directly with longer delay
                data = await stock_service._fetch_from_yahoo_safe(symbol)
                
                if data and data.get("price") and data.get("price") > 0:
                    # Verify this isn't mock data by checking if it has proper metadata
                    if data.get("exchange") and data.get("exchange") != "NASDAQ":
                        # This is likely real data
                        logger.info(f"Got real data for {symbol}: ${data['price']}")
                        
                        # Update database
                        existing = db.query(StockPrice).filter(StockPrice.symbol == symbol).first()
                        if existing:
                            existing.price = data["price"]
                            existing.previous_close = data["previous_close"]
                            existing.change = data["change"]
                            existing.change_percent = data["change_percent"]
                            existing.market_state = data["market_state"]
                            existing.currency = data["currency"]
                            existing.exchange = data["exchange"]
                            existing.updated_at = datetime.now()
                        else:
                            new_price = StockPrice(
                                symbol=symbol,
                                price=data["price"],
                                previous_close=data["previous_close"],
                                change=data["change"],
                                change_percent=data["change_percent"],
                                market_state=data["market_state"],
                                currency=data["currency"],
                                exchange=data["exchange"]
                            )
                            db.add(new_price)
                        
                        db.commit()
                        success_count += 1
                    else:
                        logger.warning(f"Got mock/invalid data for {symbol}")
                        failed_count += 1
                else:
                    logger.warning(f"No data for {symbol}")
                    failed_count += 1
                
                # Wait longer between requests to avoid rate limiting
                await asyncio.sleep(5)  # 5 seconds between each symbol
                
            except Exception as e:
                logger.error(f"Error processing {symbol}: {e}")
                failed_count += 1
                await asyncio.sleep(2)
        
        logger.info(f"Collection complete: {success_count} success, {failed_count} failed")
        
    finally:
        db.close()


if __name__ == "__main__":
    asyncio.run(collect_real_yahoo_prices())

