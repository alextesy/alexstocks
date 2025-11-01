# EC2 Migration Quickstart - U0 User Schema

## TL;DR - Is it Safe?
✅ **YES** - Creates 4 new tables only. Zero impact on existing data.

## Migration Workflow (With CI/CD)

Your CI/CD pipeline automatically deploys code changes, so the process is:

### 1️⃣ Merge to Master
```bash
# Locally (or via PR merge)
git checkout main
git merge your-feature-branch
git push origin main
```

### 2️⃣ CI/CD Deploys Automatically
Your `.github/workflows/ci.yml` will:
- ✅ Run tests
- ✅ Deploy to EC2 (`/opt/market-pulse-v2`)
- ✅ Restart `market-pulse` service
- ✅ Install dependencies via `uv sync`

**Wait for CI/CD to complete (~2-5 minutes)**

### 3️⃣ SSH to EC2 and Run Migration
```bash
# SSH into EC2
ssh your-ec2-instance

# Navigate to project (CI/CD already updated code)
cd /opt/market-pulse-v2

# Optional: Backup database first
pg_dump -h localhost -U postgres -d market_pulse > backup_$(date +%Y%m%d).sql

# Check migration status
make migrate-status   # Shows current state
make migrate-history  # Shows pending migrations

# Apply migration
make migrate-up
```

Expected output:
```
INFO  [alembic.runtime.migration] Running upgrade  -> 7a6b96aac112, create_user_tables
```

### 4️⃣ Verify
```bash
make migrate-status  # Should show: 7a6b96aac112 (head)

# Quick smoke test
curl http://localhost:8000/api/health
curl http://localhost:8000/api/articles?limit=1
```

## What Gets Created?
- `users` - Core user accounts
- `user_profiles` - Extended profile info
- `user_notification_channels` - Email/SMS/push preferences  
- `user_ticker_follows` - Tracked tickers per user

## Rollback (If Needed)
```bash
make migrate-down  # Drops the 4 new tables
```

## New Commands Available
```bash
make migrate-up          # Apply migrations
make migrate-down        # Rollback last migration
make migrate-status      # Check current state
make seed-users          # Create sample users (auto-disabled in prod)
make test-users          # Run user tests
```

## What WON'T Change?
- ✅ Existing articles, tickers, stock prices
- ✅ Reddit scraping jobs
- ✅ Sentiment analysis
- ✅ Current API endpoints
- ✅ All your data

## Environment Detection
The seed script (`make seed-users`) automatically checks:
```python
if settings.environment == "production":
    # Will refuse to run
```

Set via `.env`:
```bash
ENV=production  # or development, staging
```

## Troubleshooting

**"already exists"** → Migration ran twice, safe to ignore or:
```bash
uv run alembic stamp head
```

**Need to check database manually?**
```bash
psql -h localhost -U postgres market_pulse
\dt users*
\d users
```

**Migration hangs?** → Check database locks:
```bash
psql -c "SELECT * FROM pg_locks WHERE granted = false;"
```

---

**Bottom Line**: Additive-only migration. Safe to run anytime. 🚀

Full docs: [USER_MIGRATION_GUIDE.md](./USER_MIGRATION_GUIDE.md)

