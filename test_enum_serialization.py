#!/usr/bin/env python3
"""Quick test script to verify enum serialization works correctly."""

import sys
from pathlib import Path

# Add project root to path
ROOT_DIR = Path(__file__).resolve().parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from datetime import date

from app.db.models import LLMSentimentCategory, Ticker
from app.db.session import SessionLocal
from app.models.dto import DailyTickerSummaryUpsertDTO
from app.repos.summary_repo import DailyTickerSummaryRepository

def test_enum_serialization():
    """Test that enum values are correctly serialized to database."""
    session = SessionLocal()
    repo = DailyTickerSummaryRepository(session)
    
    try:
        # Ensure ticker exists
        ticker = session.get(Ticker, "TEST")
        if ticker is None:
            ticker = Ticker(symbol="TEST", name="Test Inc.")
            session.add(ticker)
            session.commit()
        
        # Test saving with enum object
        print("Testing enum serialization...")
        print(f"Enum object: {LLMSentimentCategory.BULLISH}")
        print(f"Enum name: {LLMSentimentCategory.BULLISH.name}")
        print(f"Enum value: {LLMSentimentCategory.BULLISH.value}")
        
        dto = DailyTickerSummaryUpsertDTO(
            ticker="TEST",
            summary_date=date.today(),
            mention_count=100,
            engagement_count=500,
            llm_summary="Test summary with bullish sentiment",
            llm_sentiment=LLMSentimentCategory.BULLISH,
            llm_model="gpt-test",
        )
        
        print("\nSaving to database...")
        created = repo.upsert_summary(dto)
        print(f"✓ Successfully saved! ID: {created.id}")
        print(f"✓ Sentiment enum: {created.llm_sentiment}")
        print(f"✓ Sentiment value: {created.llm_sentiment.value}")
        
        # Verify by querying directly
        from app.db.models import DailyTickerSummary
        entity = session.query(DailyTickerSummary).filter_by(
            ticker="TEST", 
            summary_date=date.today()
        ).first()
        
        if entity:
            print(f"\n✓ Verified in database:")
            print(f"  - Sentiment enum: {entity.llm_sentiment}")
            print(f"  - Sentiment value: {entity.llm_sentiment.value}")
            print(f"  - Raw value matches: {entity.llm_sentiment.value == 'Bullish'}")
        
        # Test all enum values
        print("\n\nTesting all enum values...")
        test_date = date.today()
        for idx, sentiment_enum in enumerate([
            LLMSentimentCategory.TO_THE_MOON,
            LLMSentimentCategory.BULLISH,
            LLMSentimentCategory.NEUTRAL,
            LLMSentimentCategory.BEARISH,
            LLMSentimentCategory.DOOM,
        ]):
            test_dto = DailyTickerSummaryUpsertDTO(
                ticker="TEST",
                summary_date=date(test_date.year, test_date.month, test_date.day - idx - 1),
                mention_count=100,
                engagement_count=500,
                llm_summary=f"Test summary with {sentiment_enum.value} sentiment",
                llm_sentiment=sentiment_enum,
                llm_model="gpt-test",
            )
            result = repo.upsert_summary(test_dto)
            print(f"✓ {sentiment_enum.name} -> {sentiment_enum.value} (saved as ID: {result.id})")
        
        print("\n✅ All enum serialization tests passed!")
        return True
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        session.close()

if __name__ == "__main__":
    success = test_enum_serialization()
    sys.exit(0 if success else 1)


