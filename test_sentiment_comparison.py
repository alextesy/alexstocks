#!/usr/bin/env python3
"""Test script to compare VADER vs LLM sentiment analysis."""

import logging
import sys
from typing import List, Tuple

from app.services.sentiment import get_sentiment_service
from app.services.hybrid_sentiment import get_hybrid_sentiment_service

logger = logging.getLogger(__name__)


def setup_logging(verbose: bool = False) -> None:
    """Setup logging configuration."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )


def test_sentiment_comparison() -> None:
    """Compare VADER vs LLM sentiment analysis on financial text examples."""
    setup_logging(True)
    
    # Test cases with expected sentiment
    test_cases = [
        ("AAPL stock is soaring to new heights! Great earnings report!", "positive"),
        ("TSLA is crashing hard, terrible news for investors", "negative"),
        ("The market is stable today with no significant changes", "neutral"),
        ("NVDA earnings beat expectations significantly", "positive"),
        ("This is a disaster for the company and shareholders", "negative"),
        ("Stock price increased by 5% in today's trading session", "positive"),
        ("Company reported disappointing quarterly results", "negative"),
        ("The quarterly report shows mixed results", "neutral"),
        ("Investors are bullish on the company's future prospects", "positive"),
        ("Market volatility is causing significant losses", "negative"),
        ("The stock price remained unchanged throughout the day", "neutral"),
        ("Outstanding performance this quarter exceeded all expectations", "positive"),
        ("Severe market downturn affecting all sectors", "negative"),
        ("Regular trading session with normal volume", "neutral"),
        ("Revolutionary new product launch drives investor confidence", "positive"),
    ]
    
    print("=" * 80)
    print("SENTIMENT ANALYSIS COMPARISON: VADER vs LLM")
    print("=" * 80)
    
    # Initialize services
    try:
        vader_service = get_sentiment_service()
        print("✅ VADER service initialized")
    except Exception as e:
        print(f"❌ VADER service failed: {e}")
        return
    
    try:
        hybrid_service = get_hybrid_sentiment_service()
        print("✅ Hybrid service initialized")
        service_info = hybrid_service.get_service_info()
        print(f"   Service info: {service_info}")
    except Exception as e:
        print(f"❌ Hybrid service failed: {e}")
        return
    
    print("\n" + "=" * 80)
    print("COMPARISON RESULTS")
    print("=" * 80)
    
    vader_correct = 0
    llm_correct = 0
    total_tests = len(test_cases)
    
    for i, (text, expected) in enumerate(test_cases, 1):
        print(f"\n{i:2d}. {text}")
        print(f"    Expected: {expected.upper()}")
        
        # VADER analysis
        try:
            vader_score = vader_service.analyze_sentiment(text)
            vader_label = vader_service.get_sentiment_label(vader_score)
            vader_match = vader_label.lower() == expected
            if vader_match:
                vader_correct += 1
            print(f"    VADER:   {vader_label:8} ({vader_score:6.3f}) {'✅' if vader_match else '❌'}")
        except Exception as e:
            print(f"    VADER:   ERROR - {e}")
        
        # LLM analysis
        try:
            llm_score = hybrid_service.analyze_sentiment(text)
            llm_label = hybrid_service.get_sentiment_label(llm_score)
            llm_match = llm_label.lower() == expected
            if llm_match:
                llm_correct += 1
            print(f"    LLM:     {llm_label:8} ({llm_score:6.3f}) {'✅' if llm_match else '❌'}")
        except Exception as e:
            print(f"    LLM:     ERROR - {e}")
    
    # Summary
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print(f"Total test cases: {total_tests}")
    print(f"VADER accuracy:   {vader_correct}/{total_tests} ({vader_correct/total_tests*100:.1f}%)")
    print(f"LLM accuracy:     {llm_correct}/{total_tests} ({llm_correct/total_tests*100:.1f}%)")
    
    if llm_correct > vader_correct:
        print("🏆 LLM sentiment analysis performed better!")
    elif vader_correct > llm_correct:
        print("🏆 VADER sentiment analysis performed better!")
    else:
        print("🤝 Both methods performed equally well!")


def test_performance() -> None:
    """Test performance comparison between VADER and LLM."""
    import time
    
    test_text = "AAPL stock is performing exceptionally well with strong earnings growth and positive market sentiment."
    
    print("\n" + "=" * 80)
    print("PERFORMANCE COMPARISON")
    print("=" * 80)
    
    # VADER performance
    try:
        vader_service = get_sentiment_service()
        start_time = time.time()
        for _ in range(10):
            vader_service.analyze_sentiment(test_text)
        vader_time = time.time() - start_time
        print(f"VADER: {vader_time:.3f}s for 10 analyses ({vader_time/10*1000:.1f}ms per analysis)")
    except Exception as e:
        print(f"VADER performance test failed: {e}")
    
    # LLM performance
    try:
        hybrid_service = get_hybrid_sentiment_service()
        start_time = time.time()
        for _ in range(10):
            hybrid_service.analyze_sentiment(test_text)
        llm_time = time.time() - start_time
        print(f"LLM:   {llm_time:.3f}s for 10 analyses ({llm_time/10*1000:.1f}ms per analysis)")
        
        if llm_time > vader_time:
            speedup = llm_time / vader_time
            print(f"VADER is {speedup:.1f}x faster than LLM")
        else:
            speedup = vader_time / llm_time
            print(f"LLM is {speedup:.1f}x faster than VADER")
            
    except Exception as e:
        print(f"LLM performance test failed: {e}")


def main() -> None:
    """Main function."""
    try:
        test_sentiment_comparison()
        test_performance()
    except KeyboardInterrupt:
        print("\nTest interrupted by user")
    except Exception as e:
        print(f"Test failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
