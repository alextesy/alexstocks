"""Migrate ticker table to support expanded ticker data."""

import csv
import json
import logging
from pathlib import Path

from sqlalchemy import text

from app.db.models import Ticker
from app.db.session import SessionLocal

logger = logging.getLogger(__name__)


def migrate_ticker_table():
    """Migrate the ticker table to include new columns and data."""
    logger.info("Starting ticker table migration...")
    
    db = SessionLocal()
    try:
        # Add new columns to existing table
        logger.info("Adding new columns to ticker table...")
        
        alter_commands = [
            "ALTER TABLE ticker ADD COLUMN IF NOT EXISTS exchange VARCHAR(50)",
            "ALTER TABLE ticker ADD COLUMN IF NOT EXISTS sources JSONB DEFAULT '[]'::jsonb",
            "ALTER TABLE ticker ADD COLUMN IF NOT EXISTS is_sp500 BOOLEAN DEFAULT FALSE",
            "ALTER TABLE ticker ADD COLUMN IF NOT EXISTS cik VARCHAR(20)"
        ]
        
        for command in alter_commands:
            try:
                db.execute(text(command))
                db.commit()
                logger.info(f"Executed: {command}")
            except Exception as e:
                logger.warning(f"Command may have already been executed: {command} - {e}")
                db.rollback()
        
        # Create indexes
        logger.info("Creating indexes...")
        
        index_commands = [
            "CREATE INDEX IF NOT EXISTS ticker_exchange_idx ON ticker(exchange)",
            "CREATE INDEX IF NOT EXISTS ticker_is_sp500_idx ON ticker(is_sp500)",
            "CREATE INDEX IF NOT EXISTS ticker_cik_idx ON ticker(cik)"
        ]
        
        for command in index_commands:
            try:
                db.execute(text(command))
                db.commit()
                logger.info(f"Created index: {command}")
            except Exception as e:
                logger.warning(f"Index may already exist: {command} - {e}")
                db.rollback()
        
        # Load and update ticker data
        logger.info("Loading expanded ticker data...")
        
        csv_path = Path("data/tickers_core.csv")
        if not csv_path.exists():
            logger.error("Expanded ticker CSV not found")
            return False
        
        # Update existing tickers and insert new ones
        logger.info("Updating ticker data...")
        
        tickers_updated = 0
        tickers_inserted = 0
        batch_size = 1000
        
        with open(csv_path, 'r') as f:
            reader = csv.DictReader(f)
            
            for row in reader:
                # Parse sources
                sources = []
                if row.get('sources'):
                    sources = row['sources'].split(',')
                
                # Parse aliases
                aliases = []
                if row.get('aliases'):
                    try:
                        aliases = json.loads(row['aliases'])
                    except json.JSONDecodeError:
                        logger.warning(f"Invalid aliases for {row['symbol']}: {row['aliases']}")
                
                # Parse boolean
                is_sp500 = row.get('is_sp500', '').lower() in ('true', '1', 'yes')
                
                symbol = row['symbol']
                
                # Check if ticker exists
                existing_ticker = db.query(Ticker).filter(Ticker.symbol == symbol).first()
                
                if existing_ticker:
                    # Update existing ticker
                    existing_ticker.name = row['name']
                    existing_ticker.exchange = row.get('exchange') or None
                    existing_ticker.sources = sources
                    existing_ticker.aliases = aliases
                    existing_ticker.is_sp500 = is_sp500
                    existing_ticker.cik = row.get('cik') or None
                    tickers_updated += 1
                else:
                    # Insert new ticker
                    ticker_data = {
                        'symbol': symbol,
                        'name': row['name'],
                        'exchange': row.get('exchange') or None,
                        'sources': sources,
                        'aliases': aliases,
                        'is_sp500': is_sp500,
                        'cik': row.get('cik') or None
                    }
                    
                    ticker = Ticker(**ticker_data)
                    db.add(ticker)
                    tickers_inserted += 1
                
                # Commit in batches
                if (tickers_updated + tickers_inserted) % batch_size == 0:
                    db.commit()
                    logger.info(f"Processed {tickers_updated + tickers_inserted} tickers (updated: {tickers_updated}, inserted: {tickers_inserted})...")
            
            # Final commit
            db.commit()
        
        logger.info(f"Successfully updated {tickers_updated} tickers and inserted {tickers_inserted} new tickers")
        
        # Verify data
        ticker_count = db.execute(text("SELECT COUNT(*) FROM ticker")).scalar()
        sp500_count = db.execute(text("SELECT COUNT(*) FROM ticker WHERE is_sp500 = true")).scalar()
        
        logger.info(f"Verification - Total tickers: {ticker_count}, S&P 500: {sp500_count}")
        
        return True
        
    except Exception as e:
        logger.error(f"Migration failed: {e}")
        db.rollback()
        return False
    finally:
        db.close()




def main():
    """Main migration function."""
    logging.basicConfig(level=logging.INFO)
    
    success = migrate_ticker_table()
    
    if success:
        logger.info("Ticker table migration completed successfully!")
    else:
        logger.error("Ticker table migration failed!")
        exit(1)


if __name__ == "__main__":
    main()
