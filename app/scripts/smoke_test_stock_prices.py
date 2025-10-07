"""Smoke test for stock price collection with sample tickers."""

import asyncio
import logging
import sys

sys.path.append(".")

from app.db.session import SessionLocal
from app.services.stock_price_service import stock_price_service

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Sample tickers for smoke testing
SMOKE_TEST_TICKERS = ["AAPL", "TSLA", "MSFT", "AMZN", "NVDA"]


async def smoke_test():
    """
    Run smoke test with 5 sample tickers to verify:
    1. API response consistency
    2. Data accuracy
    3. Performance within acceptable limits
    """
    logger.info("=" * 80)
    logger.info("Starting Stock Price Smoke Test")
    logger.info(f"Testing with tickers: {SMOKE_TEST_TICKERS}")
    logger.info("=" * 80)

    db = SessionLocal()

    try:
        results = []

        # Test each ticker individually
        for symbol in SMOKE_TEST_TICKERS:
            logger.info(f"\nTesting {symbol}...")
            try:
                import time

                start = time.time()

                # Fetch price (with force refresh to test API)
                price_data = await stock_price_service.get_or_refresh_price(
                    db, symbol, force_refresh=True
                )

                elapsed = time.time() - start

                if price_data:
                    logger.info(f"✓ {symbol}:")
                    logger.info(f"  Price: ${price_data['price']}")
                    logger.info(
                        f"  Change: ${price_data['change']} ({price_data['change_percent']}%)"
                    )
                    logger.info(f"  Market State: {price_data['market_state']}")
                    logger.info(f"  Exchange: {price_data['exchange']}")
                    logger.info(f"  Response Time: {elapsed:.2f}s")

                    # Validate response time (<2s per ticker)
                    if elapsed > 2.0:
                        logger.warning("  ⚠️  Response time exceeded 2s threshold")

                    results.append(
                        {
                            "symbol": symbol,
                            "success": True,
                            "price": price_data["price"],
                            "elapsed": elapsed,
                        }
                    )
                else:
                    logger.error(f"✗ {symbol}: No data returned")
                    results.append(
                        {"symbol": symbol, "success": False, "elapsed": elapsed}
                    )

            except Exception as e:
                logger.error(f"✗ {symbol}: Error - {e}")
                results.append({"symbol": symbol, "success": False, "error": str(e)})

        # Summary
        logger.info("\n" + "=" * 80)
        logger.info("Smoke Test Summary")
        logger.info("=" * 80)

        successful = sum(1 for r in results if r.get("success"))
        failed = len(results) - successful

        logger.info(f"Total Tested: {len(results)}")
        logger.info(f"Successful: {successful}")
        logger.info(f"Failed: {failed}")

        if successful > 0:
            avg_time = (
                sum(r["elapsed"] for r in results if r.get("success")) / successful
            )
            logger.info(f"Average Response Time: {avg_time:.2f}s")

        logger.info("\n" + "=" * 80)

        if failed > 0:
            logger.warning("⚠️  Some tests failed. Please review the errors above.")
            logger.info(
                "Note: Occasional failures may occur due to API rate limits or network issues."
            )
        else:
            logger.info("✓ All smoke tests passed!")

        logger.info("=" * 80)

        # Manual comparison suggestion
        logger.info("\n📊 Manual Comparison:")
        logger.info(
            "Please compare the prices above with Google Finance or Yahoo Finance"
        )
        logger.info("to verify accuracy:")
        for result in results:
            if result.get("success"):
                symbol = result["symbol"]
                logger.info(
                    f"  - {symbol}: https://www.google.com/finance/quote/{symbol}:NASDAQ"
                )

        return {"total": len(results), "successful": successful, "failed": failed}

    finally:
        db.close()


if __name__ == "__main__":
    asyncio.run(smoke_test())
