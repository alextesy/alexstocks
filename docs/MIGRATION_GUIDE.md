# Database Migration Guide - EC2 Deployment

## Overview
This guide shows how to manually run the stock_price table expansion migration on your EC2 instance after deploying the code changes.

---

## Prerequisites

Before running the migration:
1. ✅ Deploy the updated code to EC2
2. ✅ Ensure the EC2 instance has access to the database
3. ✅ Verify environment variables are set (DATABASE_URL)

---

## Migration Steps

### Step 1: SSH into EC2 Instance

```bash
# From your local machine
ssh -i your-key.pem ec2-user@your-ec2-instance
```

### Step 2: Navigate to Project Directory

```bash
# Assuming your project is in /home/ec2-user/market-pulse-v2
cd /home/ec2-user/market-pulse-v2
```

### Step 3: Check Current Database Connection

```bash
# Verify environment variables are set
echo $DATABASE_URL

# Or check the .env file
cat .env | grep DATABASE_URL
```

### Step 4: Run the Migration Script

**Option A: Using UV (Recommended)**
```bash
uv run python app/scripts/expand_stock_price_table.py
```

**Option B: Using activated venv**
```bash
source .venv/bin/activate
python app/scripts/expand_stock_price_table.py
```

**Option C: Using system Python (if uv not available)**
```bash
python3 app/scripts/expand_stock_price_table.py
```

### Step 5: Verify Migration Success

You should see output like:
```
================================================================================
Expanding stock_price table with Phase 1 enhancements...
================================================================================

📊 Adding intraday trading data columns...
  ✓ Added column: open (FLOAT)
  ✓ Added column: day_high (FLOAT)
  ✓ Added column: day_low (FLOAT)
  ✓ Added column: volume (BIGINT)

💹 Adding bid/ask spread columns...
  ✓ Added column: bid (FLOAT)
  ✓ Added column: ask (FLOAT)
  ✓ Added column: bid_size (INTEGER)
  ✓ Added column: ask_size (INTEGER)

💼 Adding market metrics columns...
  ✓ Added column: market_cap (BIGINT)
  ✓ Added column: shares_outstanding (BIGINT)
  ✓ Added column: average_volume (BIGINT)
  ✓ Added column: average_volume_10d (BIGINT)

================================================================================
✅ Migration completed successfully!
================================================================================
```

---

## Verification

### Check Database Directly

**Option 1: Using psql (PostgreSQL)**
```bash
# Connect to database
psql $DATABASE_URL

# Check the table structure
\d stock_price

# Should show all new columns:
# - open
# - day_high
# - day_low
# - volume
# - bid
# - ask
# - bid_size
# - ask_size
# - market_cap
# - shares_outstanding
# - average_volume
# - average_volume_10d

# Exit psql
\q
```

**Option 2: Using Python**
```bash
# Quick verification script
cat > verify_migration.py << 'EOF'
import sys
sys.path.append(".")

from sqlalchemy import inspect
from app.db.session import engine

inspector = inspect(engine)
columns = [col['name'] for col in inspector.get_columns('stock_price')]

print("Current stock_price columns:")
for col in sorted(columns):
    print(f"  - {col}")

new_columns = ['open', 'day_high', 'day_low', 'volume', 'bid', 'ask',
               'bid_size', 'ask_size', 'market_cap', 'shares_outstanding',
               'average_volume', 'average_volume_10d']

print("\nMigration status:")
for col in new_columns:
    status = "✓" if col in columns else "✗"
    print(f"  {status} {col}")
EOF

uv run python verify_migration.py
rm verify_migration.py
```

### Test Data Collection

After migration, run the stock price collector to populate the new fields:

```bash
# Run the collector job
cd jobs
uv run python jobs/stock_price_collector.py
```

Or using make:
```bash
make stock_price_collector
```

---

## Troubleshooting

### Issue: "Permission denied" or "No such file or directory"

**Solution:** Ensure you're in the correct directory and have proper permissions

```bash
pwd  # Should show /home/ec2-user/market-pulse-v2 or similar
ls app/scripts/expand_stock_price_table.py  # Should exist
```

### Issue: "ModuleNotFoundError: No module named 'app'"

**Solution:** Make sure you're running from the project root directory

```bash
cd /home/ec2-user/market-pulse-v2
# Then run the migration
```

### Issue: "connection refused" or database connection error

**Solution:** Check database connectivity and environment variables

```bash
# Test database connection
psql $DATABASE_URL -c "SELECT 1;"

# Check .env file
cat .env | grep DATABASE

# Reload environment variables if needed
source .env
```

### Issue: "Column already exists"

**Solution:** The migration has already been run. This is safe to ignore.

The script checks for existing columns and will ask if you want to continue. Existing data is preserved.

### Issue: uv command not found

**Solution:** Install uv or use alternative method

```bash
# Check if uv is installed
which uv

# If not, use venv method
source .venv/bin/activate
python app/scripts/expand_stock_price_table.py

# Or install uv
curl -LsSf https://astral.sh/uv/install.sh | sh
```

---

## Rollback (If Needed)

If you need to rollback the migration:

```sql
-- Connect to database
psql $DATABASE_URL

-- Drop the new columns
ALTER TABLE stock_price DROP COLUMN IF EXISTS open;
ALTER TABLE stock_price DROP COLUMN IF EXISTS day_high;
ALTER TABLE stock_price DROP COLUMN IF EXISTS day_low;
ALTER TABLE stock_price DROP COLUMN IF EXISTS volume;
ALTER TABLE stock_price DROP COLUMN IF EXISTS bid;
ALTER TABLE stock_price DROP COLUMN IF EXISTS ask;
ALTER TABLE stock_price DROP COLUMN IF EXISTS bid_size;
ALTER TABLE stock_price DROP COLUMN IF EXISTS ask_size;
ALTER TABLE stock_price DROP COLUMN IF EXISTS market_cap;
ALTER TABLE stock_price DROP COLUMN IF EXISTS shares_outstanding;
ALTER TABLE stock_price DROP COLUMN IF EXISTS average_volume;
ALTER TABLE stock_price DROP COLUMN IF EXISTS average_volume_10d;
```

**Note:** This will delete the data in these columns. Only rollback if absolutely necessary.

---

## Production Deployment Checklist

- [ ] Deploy updated code to EC2
- [ ] SSH into EC2 instance
- [ ] Navigate to project directory
- [ ] Verify DATABASE_URL is set
- [ ] Run migration script
- [ ] Verify migration success
- [ ] Run stock price collector
- [ ] Check logs for any errors
- [ ] Verify new fields are populated in database

---

## Database Connection Methods

### If using RDS (PostgreSQL):

```bash
# From EC2, connection string should be in .env
cat .env | grep DATABASE_URL

# Format should be:
# DATABASE_URL=postgresql://username:password@rds-endpoint:5432/dbname
```

### If using local SQLite (not recommended for production):

The migration will work with SQLite too, but performance may be impacted.

---

## Monitoring After Migration

After running the migration, monitor:

1. **Check stock_price_collector logs**
   ```bash
   # If using systemd or similar
   journalctl -u stock-price-collector -f

   # Or check application logs
   tail -f logs/stock_price_collector.log
   ```

2. **Verify data is being populated**
   ```sql
   -- Connect to database
   psql $DATABASE_URL

   -- Check recent records
   SELECT symbol, price, volume, market_cap, day_high, day_low, updated_at
   FROM stock_price
   ORDER BY updated_at DESC
   LIMIT 10;
   ```

3. **Check for NULL values (expected for old records)**
   ```sql
   -- Old records will have NULL in new fields until next update
   SELECT
     COUNT(*) as total_records,
     COUNT(volume) as records_with_volume,
     COUNT(market_cap) as records_with_market_cap
   FROM stock_price;
   ```

---

## Alternative: Manual SQL Migration

If you prefer to run the migration manually via SQL:

```bash
psql $DATABASE_URL
```

Then execute:

```sql
-- Intraday trading data
ALTER TABLE stock_price ADD COLUMN IF NOT EXISTS open FLOAT;
ALTER TABLE stock_price ADD COLUMN IF NOT EXISTS day_high FLOAT;
ALTER TABLE stock_price ADD COLUMN IF NOT EXISTS day_low FLOAT;
ALTER TABLE stock_price ADD COLUMN IF NOT EXISTS volume BIGINT;

-- Bid/Ask spread
ALTER TABLE stock_price ADD COLUMN IF NOT EXISTS bid FLOAT;
ALTER TABLE stock_price ADD COLUMN IF NOT EXISTS ask FLOAT;
ALTER TABLE stock_price ADD COLUMN IF NOT EXISTS bid_size INTEGER;
ALTER TABLE stock_price ADD COLUMN IF NOT EXISTS ask_size INTEGER;

-- Market metrics
ALTER TABLE stock_price ADD COLUMN IF NOT EXISTS market_cap BIGINT;
ALTER TABLE stock_price ADD COLUMN IF NOT EXISTS shares_outstanding BIGINT;
ALTER TABLE stock_price ADD COLUMN IF NOT EXISTS average_volume BIGINT;
ALTER TABLE stock_price ADD COLUMN IF NOT EXISTS average_volume_10d BIGINT;

-- Verify
\d stock_price
```

---

## Questions?

If you encounter issues:
1. Check the troubleshooting section above
2. Verify your database connection
3. Ensure all environment variables are set correctly
4. Check application logs for detailed error messages

The migration is **safe** and **reversible** - existing data is preserved and all new columns are nullable.
