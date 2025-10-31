# User Schema Migration Guide

## Overview
This guide explains how to safely apply the U0 user schema migration on your EC2 production machine.

## ✅ Safety Analysis

### Is this migration safe?
**YES** - This migration is **completely safe** to run on production because:

1. **No existing tables are modified** - All changes are additive
2. **New tables only** - Creates 4 new tables:
   - `users`
   - `user_profiles` 
   - `user_notification_channels`
   - `user_ticker_follows`

3. **No data loss risk** - Existing data in `article`, `ticker`, `stock_price`, etc. is untouched

4. **Foreign key is safe** - The only FK dependency is `user_ticker_follows.ticker → ticker.symbol`
   - This references the existing `ticker` table
   - No cascading effects on existing data

5. **Reversible** - Can be rolled back cleanly with `make migrate-down`

### What won't be affected?
- ✅ All existing articles
- ✅ All existing tickers  
- ✅ All stock price data
- ✅ Reddit scraping functionality
- ✅ Sentiment analysis
- ✅ Current API endpoints

## Migration Steps (EC2)

### 1. Deploy via CI/CD

Your CI/CD pipeline (`.github/workflows/ci.yml`) automatically handles deployment when you merge to master:

```bash
# Locally (or via GitHub PR merge)
git checkout main
git merge your-feature-branch
git push origin main
```

The CI/CD will:
- ✅ Run all tests
- ✅ SSH to EC2 and pull latest code to `/opt/market-pulse-v2`
- ✅ Install dependencies via `uv sync` (includes alembic + python-jose)
- ✅ Restart the `market-pulse` service

**Wait for CI/CD to complete (~2-5 minutes)** before proceeding.

### 2. SSH to EC2 (After CI/CD Completes)

```bash
# SSH into EC2
ssh your-ec2-instance

# Navigate to project (already updated by CI/CD)
cd /opt/market-pulse-v2

# Verify latest code is deployed
git log -1 --oneline

# Verify you have the alembic directory
ls -la alembic/
```

### 3. Check Current Migration Status

```bash
# See current migration state
make migrate-status

# If this is your first time using Alembic, you'll see:
# INFO  [alembic.runtime.migration] Context impl PostgresqlImpl.
# INFO  [alembic.runtime.migration] Will assume transactional DDL.
```

### 4. Preview the Migration (Optional but Recommended)

```bash
# Show what migrations exist
make migrate-history

# Check if database is in sync with models
make migrate-check

# You should see the user tables migration: 7a6b96aac112_create_user_tables
```

### 5. Backup Database (Recommended)

```bash
# Create a backup before migration
pg_dump -h localhost -U your_user -d market_pulse > backup_before_user_migration_$(date +%Y%m%d_%H%M%S).sql

# Or if using Docker Postgres:
docker exec postgres pg_dump -U your_user market_pulse > backup_before_user_migration_$(date +%Y%m%d_%H%M%S).sql
```

### 6. Run the Migration

```bash
# Apply all pending migrations
make migrate-up

# Expected output:
# INFO  [alembic.runtime.migration] Context impl PostgresqlImpl.
# INFO  [alembic.runtime.migration] Will assume transactional DDL.
# INFO  [alembic.runtime.migration] Running upgrade  -> 7a6b96aac112, create_user_tables
```

### 7. Verify Migration Success

```bash
# Check migration status
make migrate-status

# Should show: 7a6b96aac112 (head)

# Verify tables were created
psql -h localhost -U your_user -d market_pulse -c "\dt users*"

# Expected output:
#                 List of relations
#  Schema |           Name               | Type  |  Owner
# --------+------------------------------+-------+---------
#  public | users                        | table | your_user
#  public | user_notification_channels   | table | your_user
#  public | user_profiles                | table | your_user
#  public | user_ticker_follows          | table | your_user
```

### 8. Test Basic Functionality

```bash
# Run user tests (optional, but recommended)
make test-users

# Seed sample users (DEV/STAGING ONLY - auto-disabled in production)
make seed-users
```

### 9. Verify Existing Functionality Still Works

```bash
# Test that existing API still works
curl http://localhost:8000/api/health

# Check recent articles still load
curl http://localhost:8000/api/articles?limit=10

# Verify ticker data intact
curl http://localhost:8000/api/ticker/AAPL
```

## Rollback Plan (If Needed)

If something goes wrong (unlikely):

```bash
# Rollback the last migration
make migrate-down

# This will drop the 4 new user tables
# Your existing data remains untouched
```

## Quick Reference: New Make Commands

```bash
# Migration commands
make migrate-status      # Show current migration version
make migrate-history     # Show all migrations
make migrate-up          # Apply pending migrations
make migrate-down        # Rollback last migration
make migrate-check       # Check if migrations needed
make migrate-create NAME=description  # Create new migration

# User management
make seed-users          # Seed sample users (disabled in prod)
make test-users          # Run user tests
```

## Environment-Specific Notes

### Development/Local
```bash
# Full workflow:
git pull
uv sync
make migrate-up
make seed-users  # OK in dev
make test-users
```

### Staging
```bash
# Same as dev, but be cautious with seed data:
git pull
uv sync
make migrate-up
make seed-users  # OK if environment != "production"
```

### Production (EC2 with CI/CD)
```bash
# 1. Merge to master (locally or via GitHub PR)
git push origin main

# 2. Wait for CI/CD to deploy (~2-5 minutes)
# CI/CD automatically: pulls code, installs deps, restarts service

# 3. SSH to EC2 and run migration
ssh your-ec2-instance
cd /opt/market-pulse-v2

# Backup first!
pg_dump [...] > backup.sql

# Apply migration
make migrate-up

# Verify
make migrate-status

# Test existing functionality
curl http://localhost:8000/api/health
```

## Troubleshooting

### Issue: "relation already exists"
**Cause**: Tables were manually created or migration ran twice  
**Solution**: Either drop the tables manually or mark migration as applied:
```bash
uv run alembic stamp head
```

### Issue: "no such table: ticker"
**Cause**: Ticker table doesn't exist (shouldn't happen)  
**Solution**: Run your existing `db-init` first:
```bash
make db-init
make seed-tickers
make migrate-up
```

### Issue: Migration hangs
**Cause**: Database lock or active connections  
**Solution**: 
```bash
# Check for locks
psql -c "SELECT * FROM pg_locks WHERE granted = false;"

# Kill blocking processes if needed
# Then retry migration
```

### Issue: "Can't locate revision"
**Cause**: Alembic state out of sync  
**Solution**:
```bash
# Check what's actually in database
psql -c "SELECT * FROM alembic_version;"

# Stamp to correct version
uv run alembic stamp 7a6b96aac112
```

## Post-Migration Checklist

After successful migration:

- [ ] Migration status shows `7a6b96aac112 (head)`
- [ ] All 4 user tables exist in database
- [ ] Existing API endpoints still work
- [ ] Reddit scraping continues normally
- [ ] Stock price collection works
- [ ] No errors in application logs
- [ ] Can create test user via repository (if testing)

## Next Steps

After migration is complete:

1. **U1**: API endpoints for user management (coming next)
2. **U2**: OAuth integration
3. **U3**: User preferences UI
4. **U4**: Notification system

## Questions?

- Check logs: `journalctl -u your-service-name -f`
- Alembic docs: https://alembic.sqlalchemy.org/
- Open issue on GitHub for specific problems

---

**Remember**: This migration is **additive only** - it creates new tables without touching existing ones. Your data is safe! 🛡️

