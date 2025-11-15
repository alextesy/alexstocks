# AlexStocks

**Real-time Reddit market intelligence with hybrid LLM sentiment, hourly mention analytics, Gmail-powered auth, and battle-tested cloud automation.**

[![Python](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.104+-green.svg)](https://fastapi.tiangolo.com/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-blue.svg)](https://www.postgresql.org/)

> 🆕 Recent additions: Google OAuth with JWT-backed sessions, automatic timezone detection, GA4 user analytics, SES-powered daily summaries, Redis-backed API budgets, hourly mentions API, concurrent Yahoo Finance collectors, and AWS ECS Fargate cron fleet managed by Terraform + GitHub Actions.

_Formerly referred to internally as Market Pulse v2; the public-facing experience, docs, and infrastructure now ship as **AlexStocks**._

---

## Feature Overview

### Reddit & Data Ingestion
- Unified `ingest.reddit_scraper_cli` with **incremental**, **backfill**, and **status** modes (PRAW + robust retry/backoff).
- Tracks discussion threads in `reddit_thread` and maintains per-source runtime metrics in `scraping_status`.
- 15-minute production cadence backed by EventBridge + ECS Fargate (Spot) with CloudWatch Logs.
- CLI surfaces structured JSON telemetry (threads processed, ticker links, batches saved) for observability.

### Sentiment Intelligence
- `HybridSentimentService` fuses **FinBERT** LLM scores with **VADER** and automatically falls back when the LLM is neutral or unavailable.
- Jobs to override existing sentiment with LLM-only or dual-model scoring (`override_sentiment_with_llm`, `override_sentiment_dual_model`).
- `SentimentAnalyticsService` provides leaning metrics (positive vs negative share) and histogram data used by the homepage and API (`/api/sentiment/*`).
- Ticker detail pages surface sentiment timelines (day/week/month) and unique user counts per interval.

### Mention & Velocity Analytics
- `/api/mentions/hourly` aggregates linked articles per ticker over sliding windows (1–168 hours) with zero-fill gaps and UTC alignment.
- Home dashboard renders hourly mention trends with Chart.js, dynamic ticker selection, and local-time formatting.
- `VelocityService` computes activity z-scores vs configurable baselines to flag momentum tickers in UI cards.

### Stock Market Data
- Async Yahoo Finance integration with semaphore-limited concurrency (5× faster for large symbol sets) and resilient retry logic.
- `StockPrice` table stores comprehensive intraday metrics (bid/ask, market cap, volume averages).
- Historical OHLCV persists to `stock_price_history`; `stock_price_collector` job refreshes current + historical data.
- `ensure_fresh_stock_price` guarantees ticker pages hydrate live prices before rendering (default 15-minute freshness).

### Web Experience
- FastAPI + Jinja templates + Tailwind UI for browse, ticker detail, sentiment charts, and velocity badges.
- Built-in search, pagination, and multiple sort orders for tickers.
- Home page surfaces 24h sentiment lean, scraping status, and curated default tickers for the mentions chart.
- Privacy/about pages, GTM toggles, and cookie consent hooks controlled via Pydantic settings.

### Authentication & Personalization
- Gmail-only Google OAuth login backed by JWT sessions, CSRF-protected state, and account blocking controls (`/auth/login`, `/auth/callback`, `/auth/logout`, `/auth/me`).
- Browser-based timezone detection automatically syncs to `user_profiles.timezone` via `/auth/update-timezone`, enabling localized analytics and future notifications.
- GA4 instrumentation emits login/logout events plus user properties (`user_id`, timezone, auth provider) once cookie consent is granted.
- AWS SES integration delivers AlexStocks Daily Summary emails and `make send-test-email` smoke tests driven by `EMAIL_*` settings.

### Reliability & Safety Rails
- Redis-backed rate limiting middleware with per-endpoint quotas and `Retry-After` headers.
- Parameter caps (articles limit, days, hours, offset budget) enforced centrally in `settings` and validated in routing layer + tests.
- Extensive instrumentation of scraping and stock collectors with failure logging and idempotent batching.
- Split dependency graph via `pyproject.toml` (app) and `jobs/pyproject.toml` (batch) to keep production images lean.

---

## Architecture

### Core Stack
- **FastAPI** for HTTP APIs and server-rendered views.
- **SQLAlchemy 2.x** ORM with Postgres-first schema, SQLite-compatible fallbacks (`JSONBCompat`, `BigIntegerCompat`).
- **Jinja2 + Tailwind + Chart.js** for templated UI.
- **Pydantic Settings** for typed configuration sourced from `.env`.
- **uv** for virtualenv management and reproducible lock files.

### Batch & Infrastructure
- `jobs/` directory contains the Fargate-ready runtime (Dockerfile, minimal dependencies, shared code from `app/` and `jobs/ingest/`).
- **AWS ECS Fargate (Spot)** runs Reddit scraper, sentiment analysis, stock collector, and daily status tasks.
- **AWS EventBridge Scheduler** triggers tasks, while **Amazon ECR** stores container images.
- **Terraform** modules (`infrastructure/terraform`) provision IAM, networking, ECS, scheduler, and CloudWatch resources.
- **GitHub Actions** workflows build, scan, push, and deploy jobs (`.github/workflows/deploy-ecs-jobs.yml`).

### Supporting Services
- **PostgreSQL 16** via Docker Compose for local development.
- **Redis** (optional for development, required for production rate limiting) with helper targets (`make redis-up`/`redis-down`).
- **PRAW** for Reddit API access, `redis.asyncio` for rate limiting, and `yfinance` for market data.

### Database Schema (abridged)

```
┌──────────────┐        ┌──────────────────┐        ┌──────────────┐
│   Ticker     │◄──────►│  ArticleTicker   │◄──────►│   Article    │
│ symbol (PK)  │        │ article_id (FK)  │        │ id (PK)      │
│ name         │        │ ticker (FK)      │        │ source       │
│ aliases JSON │        │ confidence       │        │ title/text   │
│ exchange     │        │ matched_terms    │        │ sentiment    │
│ sources      │        └──────────────────┘        │ reddit/meta  │
└──────────────┘                                   │ published_at │
                                                   └──────────────┘

┌──────────────────┐       ┌────────────────────┐
│  RedditThread    │       │   ScrapingStatus   │
│ reddit_id (PK)   │       │ source (PK)        │
│ subreddit/type   │       │ last_scrape_at     │
│ total/scraped    │       │ items_scraped      │
│ is_complete      │       │ status/error       │
└──────────────────┘       └────────────────────┘

┌──────────────┐        ┌────────────────────┐        ┌────────────────────────┐
│ StockPrice   │        │ StockPriceHistory  │        │ StockDataCollection    │
│ symbol (PK)  │        │ id (PK)            │        │ id (PK)                │
│ price/change │        │ symbol (FK)        │        │ collection_type        │
│ bid/ask/etc  │        │ date + OHLCV       │        │ success/fail counts    │
│ updated_at   │        │ volume             │        │ duration/errors JSON   │
└──────────────┘        └────────────────────┘        └────────────────────────┘
```

---

## Directory Layout

```
market-pulse-v2/
├── app/                     # FastAPI app, services, models, templates
│   ├── main.py              # Routes (HTML + API) with rate limiting
│   ├── config.py            # Pydantic settings
│   ├── db/                  # SQLAlchemy models & session management
│   ├── services/            # Sentiment, mentions, stock data, rate limiters
│   ├── collectors/          # Local stock collection scripts
│   ├── scripts/             # DB init/seed utilities & migrations helpers
│   └── templates/           # Jinja2 templates for UI
├── jobs/                    # Containerized batch runtime for ECS
│   ├── Dockerfile
│   ├── pyproject.toml
│   ├── ingest/              # Production Reddit scraper + CLI
│   └── jobs/                # Sentiment/stock jobs executed in ECS tasks
├── infrastructure/terraform # Terraform modules for ECS/ECR/EventBridge/IAM
├── tests/                   # Pytest suite (unit, integration, regression)
├── docs/                    # Playbooks, migration guides, API docs
├── Makefile                 # Developer + ops automation
├── docker-compose.yml       # Local Postgres services
└── README.md                # You are here
```

---

## Quick Start

### Prerequisites
- **Python 3.11+** (3.12 compatible, 3.13 not yet validated)
- **[uv](https://docs.astral.sh/uv/)** for dependency management
- **Docker & Docker Compose** (local PostgreSQL)
- **Redis** (optional locally; required for production rate limiting)
- Reddit API credentials (client id/secret/user agent)

### Installation

1. **Clone and enter the repo**
   ```bash
   git clone <repository-url>
   cd market-pulse-v2
   ```

2. **Install Python dependencies**
   ```bash
   uv sync
   ```

3. **Configure environment**
   ```bash
   cp .env.example .env
   # Edit .env and add your credentials:
   # - GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET (required for authentication)
   # - DATABASE_URL (defaults to local PostgreSQL)
   # - REDDIT_CLIENT_ID / REDDIT_CLIENT_SECRET (optional, for social data)
   # - Other settings have sensible defaults
   ```

4. **Start services (Postgres + API)**
   ```bash
   make up
   # In a separate terminal, optionally start Redis for rate limiting
   make redis-up
   ```

5. **Bootstrap the database**
   ```bash
   make db-init
   make seed-tickers
   # Optionally load demo content
   make seed-sample-data
   ```

6. **Browse the app**
   - Web UI: http://localhost:8000/
   - API docs (FastAPI): http://localhost:8000/docs
   - Health check: http://localhost:8000/health

To shut down local services run `make down` (and `make redis-down` for Redis).

---

## CLI & Automation

### Reddit scraping & sentiment

```bash
make reddit-scrape-incremental             # 15-min production scraper mode
make reddit-scrape-backfill START=2025-01-01 END=2025-01-31
make reddit-scrape-status                  # Prints scraping_status + live subreddit stats
make analyze-sentiment                     # Analyze articles lacking sentiment (LLM-first)
make analyze-sentiment-reddit              # Reddit-only batch
make override-sentiment-llm                # Re-score everything with LLM
make override-sentiment-dual               # Dual-model override (LLM + VADER)
make override-sentiment-dual-recent        # 24h dual-model refresh
make scrape-and-analyze-full               # Latest daily thread scrape + sentiment
```

### Stock data jobs

```bash
make collect-stock-prices                  # Refresh current prices for all tickers
make collect-stock-prices-smart            # Skip warrants/units for faster runs
make collect-historical-data               # Persist OHLCV (default 1 month)
make collect-both-stock-data               # Current + historical in one pass
make collect-top50-prices                  # ECS production task (top tickers)
make analyze-tickers                       # Inspect ticker universe & metadata quality
```

### Quality, testing & utilities

```bash
make test                                  # Full pytest suite
make test-unit                             # Fast unit tests
make test-integration                      # Integration tests (DB required)
make test-reddit                           # Reddit ingestion regression checks
make test-sentiment                        # Sentiment-specific tests
make lint                                  # Ruff + Black --check + mypy
make lint-fix                              # Ruff --fix + Black
make security                              # Bandit scan (JSON report)
make rate-limit-smoke                      # Exercise API parameter caps + 429s
```

### Authentication & email helpers

```bash
make test-users                            # Unit tests for user repository logic
make send-test-email                       # Trigger SES-backed smoke email with current settings
```

### ECS & Terraform helpers

```bash
make build-jobs-image                      # Build batch image locally
make push-jobs-image                       # Build & push to Amazon ECR
make tf-plan && make tf-apply              # Terraform workflow
make ecs-run-scraper                       # Manually trigger Reddit scraper task
make ecs-logs-scraper                      # Tail CloudWatch logs
make schedule-enable-all                   # Toggle EventBridge schedules
```

---

## API Surface

Public JSON endpoints all include rate limiting (default 60 RPM/IP) and defensive parameter caps.

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health probe used by uptime monitors |
| `/api/scraping-status` | GET | Latest scraper run metadata from `scraping_status` |
| `/api/tickers` | GET | Paginated ticker list with search + sorting + live price data |
| `/api/ticker/{ticker}/articles` | GET | Paginated articles with sentiment for a ticker |
| `/api/ticker/{ticker}/sentiment-timeline` | GET | Day/week/month sentiment buckets (comments vs unique users) |
| `/api/mentions/hourly` | GET | Hourly mention counts for 1–168 hours (multiple tickers) |
| `/api/sentiment/histogram` | GET | Global or per-ticker sentiment distribution |
| `/api/sentiment/time-series` | GET | Positive/negative counts per day (≤90 days) |
| `/api/stock/{symbol}` | GET | Cached current stock quote (refreshes via Yahoo Finance if stale) |
| `/api/stock/{symbol}/chart` | GET | Historical + current price series sourced from DB |

HTML routes include `/`, `/browse`, `/t/{ticker}`, `/about`, and `/privacy`.

### Rate limiting & parameter guards
- Defaults configured in `app/config.py`: `rl_requests_per_minute=60`, `MAX_LIMIT_ARTICLES=100`, `MAX_DAYS_TIME_SERIES=90`, `MAX_HOURS_MENTIONS=168`, `MAX_OFFSET_ITEMS=5000`.
- `app/services/rate_limit.py` uses `redis.asyncio` with fail-open fallback (warnings logged when Redis unavailable).
- `tests/test_param_caps.py` verifies caps and produces 422/429 responses when exceeded.

---

## Deployment

- **Application**: FastAPI app runs on EC2 (systemd + Nginx reverse proxy) per `docs/deployment.md`.
- **Batch jobs**: ECS Fargate (Spot) tasks:
  - `market-pulse-reddit-scraper` (*/15 minutes)
  - `market-pulse-sentiment-analysis` (*/15 minutes)
  - `market-pulse-stock-price-collector` (*/15 minutes during market hours)
  - `market-pulse-daily-status` (daily @ 04:00 UTC)
- **Container pipeline**: GitHub Actions builds `jobs/Dockerfile`, pushes to ECR, triggers ECS deploys.
- **Infrastructure as Code**: Terraform modules define ECS cluster, IAM roles, EventBridge schedules, CloudWatch log groups, and ECR repository.
- **Secrets**: Managed via AWS Secrets Manager / GitHub Actions secrets (see `scripts/setup-aws-secrets.sh` for bootstrapping).

For detailed migration notes see `docs/ECS_MIGRATION_GUIDE.md`, `docs/ECS_MIGRATION_SUMMARY.md`, and `docs/MIGRATION_COMPLETE.md`.

---

## Testing & Quality

- **Pytest** suite across `tests/` covers FastAPI routes, sentiment services, ticker linking, Reddit ingestion, and parameter caps.
- **mypy** enforces type checking for `app/`, `jobs/jobs/`, and `tests/`.
- **Ruff** + **Black** maintain formatting and linting consistency; configured via `pyproject.toml`.
- **Bandit** optional security audit (`make security` outputs JSON report).
- `rate-limit-smoke` target hits negative scenarios (422/429) to verify API guards.
- Coverage reports available via `make test-coverage` (HTML in `htmlcov/`).

---

## Recent Highlights

- Rolled out **Google OAuth + JWT sessions** for Gmail-only sign-in, complete with `/auth/*` APIs, integration tests, and structured logging.
- Added **automatic timezone detection** that syncs browsers → `/auth/update-timezone` → `user_profiles.timezone` for localized analytics.
- Instrumented **GA4 tracking** with login/logout events, user IDs, and timezone/auth provider user properties respecting cookie consent.
- Enabled **AWS SES email delivery** for AlexStocks Daily Summary plus a `make send-test-email` smoke command and documented setup.
- Deployed **Redis-backed rate limiting** with per-endpoint quotas and automatic `Retry-After` responses.
- Added **hourly mentions analytics** powering the homepage chart and `/api/mentions/hourly`.

---

## Documentation

Key references (all in `docs/`):
- `API.md` – REST endpoint contract (rate limits, payload shapes).
- `CRON_JOBS_SUMMARY.md` – 15-minute pipeline breakdown.
- `ECS_MIGRATION_GUIDE.md` & `ECS_MIGRATION_SUMMARY.md` – Infrastructure migration details.
- `LLM_SENTIMENT_SETUP.md` – FinBERT/transformers configuration notes.
- `REDDIT_SCRAPER.md` & `REDDIT_SCRAPER_SUMMARY.md` – Scraper architecture, failure handling.
- `STOCK_COLLECTION_QUICKSTART.md` & `STOCK_DATA_COLLECTION.md` – Stock price ingestion playbooks.
- `TICKER_LINKING_IMPROVEMENTS.md` – NLP linking enhancements and heuristics.
- `TESTING.md` – Test strategy, fixtures, tagging.
- `deployment.md` & `ci-cd-setup.md` – EC2 + CI/CD operation guides.

---

## Contributing

1. Fork the repo and create a feature branch from `main`.
2. `uv sync` to install dependencies.
3. Run `make lint` and `make test` before opening a PR.
4. For scraper or job changes, exercise `make reddit-scrape-status` and relevant ECS helpers locally.
5. Include tests for new logic (unit or integration as appropriate).
6. Document new behaviour in `docs/` when applicable.

---

## License & Support

This project is available for personal and educational use.

Questions or issues? Open a ticket in your team’s tracker or reach out via the internal channel used for AlexStocks operations.

---
