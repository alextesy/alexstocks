<!--
Sync Impact Report
==================
Version change: N/A (initial) → 1.0.0
Modified principles: N/A (initial constitution)
Added sections:
  - Core Principles (7 principles)
  - Architecture & Layer Boundaries
  - Development Standards
  - Governance
Removed sections: N/A
Templates requiring updates:
  - .specify/templates/plan-template.md: ✅ Compatible (Constitution Check section exists)
  - .specify/templates/spec-template.md: ✅ Compatible (Requirements/Success Criteria align)
  - .specify/templates/tasks-template.md: ✅ Compatible (Phase structure supports principles)
Follow-up TODOs: None
-->

# AlexStocks Constitution

Real-time Reddit market intelligence with hybrid LLM sentiment, hourly mention analytics, Gmail-powered auth, and battle-tested cloud automation.

## Core Principles

### I. Layered Architecture (NON-NEGOTIABLE)

The system MUST maintain strict separation between four layers with unidirectional data flow:

```
collectors → pipelines → repos/db → api
```

**Rules:**
- **Collectors** (`jobs/ingest/`, `app/collectors/`): Fetch external data (Reddit, Yahoo Finance); write raw data to database; MUST NOT import from `api/` or call repo methods directly for reads
- **Pipelines/Services** (`app/services/`, `jobs/jobs/`): Transform, enrich, and analyze data; orchestrate business logic; MAY read from repos
- **Repos** (`app/repos/`): Encapsulate all database access; provide clean data access interface; MUST NOT contain business logic
- **API** (`app/main.py`, `app/api/`): HTTP endpoints and template rendering; MUST use DTOs for request/response; MUST NOT access database directly

**Rationale:** Cross-layer imports create circular dependencies and make testing impossible. Each layer can be tested in isolation with mocked dependencies.

### II. Type Safety & Code Quality (NON-NEGOTIABLE)

All Python code MUST pass static analysis and formatting checks before merge.

**Rules:**
- Type hints on ALL function signatures and class attributes—no `Any` escape hatches without documented justification
- `mypy --strict` MUST pass with zero errors
- `ruff check` and `black` formatting MUST pass
- After ANY code change, run in sequence:
  1. `uv run ruff check --fix .`
  2. `uv run black .`
  3. `uv run mypy .`

**Rationale:** Type errors caught at development time cost 10× less than runtime production failures. Consistent formatting eliminates bikeshedding in reviews.

### III. Configuration-Driven Design

No magic numbers, hardcoded credentials, or environment-specific values in source code.

**Rules:**
- All thresholds, limits, and tunables MUST live in `app/config.py` (Pydantic Settings) or YAML configs
- Secrets (API keys, database URLs) MUST come from environment variables (`.env` locally, Secrets Manager in production)
- Default values MUST be production-safe (fail-closed, conservative limits)
- Rate limits, pagination caps, and API budgets defined centrally: `MAX_LIMIT_ARTICLES=100`, `MAX_HOURS_MENTIONS=168`, `MAX_OFFSET_ITEMS=5000`

**Rationale:** Configuration drift is the #1 cause of "works on my machine" bugs. Centralized config enables feature flags, A/B testing, and safe rollouts.

### IV. DTO Boundaries

Data Transfer Objects (DTOs) MUST be used at all system boundaries.

**Rules:**
- API endpoints receive Pydantic models, return Pydantic models—never raw ORM objects
- Collector outputs produce validated DTOs before database writes
- Inter-service communication uses typed DTOs from `app/models/dto.py`
- `TickerLinkDTO` MUST include: `ticker`, `confidence`, `matched_terms`
- Sentiment DTOs MUST include: `prob_pos`, `prob_neg`, `prob_neu`, `score`, `method`

**Rationale:** DTOs create explicit contracts that can be versioned, validated, and tested independently from implementation details.

### V. UTC-First Temporal Data

All datetime values MUST be timezone-aware and stored in UTC.

**Rules:**
- Use `datetime.now(timezone.utc)` or `datetime.now(tz=UTC)`—never naive `datetime.now()`
- Database columns: `TIMESTAMPTZ` (PostgreSQL) or equivalent
- API responses include ISO 8601 timestamps with `Z` suffix
- User-facing display converts to user timezone (from `user_profiles.timezone`) only at render time
- Temporal queries use UTC ranges; gap-filling aligns to UTC hour/day boundaries

**Rationale:** Timezone bugs are the hardest to reproduce and debug. UTC-first eliminates DST edge cases and ensures consistent analytics across timezones.

### VI. Idempotent & Resumable Operations

All data ingestion and batch jobs MUST be safely re-runnable.

**Rules:**
- Database writes use `ON CONFLICT` upserts keyed on natural identifiers (`article.url UNIQUE`, `reddit_thread.reddit_id`)
- Collectors track progress in `scraping_status` table for observability and resumption
- Jobs MUST be interruptible at any batch boundary without data corruption
- Backfill operations MUST accept `--since` / `--until` parameters for incremental runs
- Duplicate detection happens before expensive processing (sentiment analysis, LLM calls)

**Rationale:** Distributed systems fail partially. Idempotent operations allow retry-based error recovery without manual intervention or data cleanup.

### VII. Test-Driven Confidence

Automated tests MUST validate behavior before merge; critical paths require integration coverage.

**Rules:**
- **Unit tests**: Pure functions with tiny fixtures; property-based testing where useful (linker, sentiment scoring)
- **Integration tests**: Full pipeline validation with real database (PostgreSQL via Docker Compose)
- **All test files MUST live in `tests/` directory**—never in root or alongside source
- New endpoints require contract tests validating request/response shapes and error codes
- Sentiment, ticker linking, and Reddit parsing have dedicated test suites with real-world edge cases (meme language, Unicode, sarcasm)
- `make test` MUST pass before any PR merge

**Rationale:** Tests are executable documentation. They catch regressions, enable refactoring confidence, and serve as living specification for behavior.

## Architecture & Layer Boundaries

### Technology Stack

| Layer | Technology | Notes |
|-------|------------|-------|
| Runtime | Python 3.11+ | 3.12 compatible; 3.13 not yet validated |
| API | FastAPI + Jinja2 | Server-rendered templates + JSON endpoints |
| ORM | SQLAlchemy 2.x | Sync operations with psycopg; no async mixing |
| Database | PostgreSQL 16 | SQLite fallback for tests only |
| Cache | Redis | Required for production rate limiting |
| Packaging | uv | Lock files for reproducible builds |
| Containers | Docker | ECS Fargate (Spot) for batch jobs |
| IaC | Terraform | `infrastructure/terraform/` modules |
| CI/CD | GitHub Actions | Build, lint, test, deploy pipelines |

### Directory Structure

```
market-pulse-v2/
├── app/                     # FastAPI application
│   ├── main.py              # Routes (HTML + API) with rate limiting
│   ├── config.py            # Pydantic settings (single source of config)
│   ├── api/                  # API route modules
│   │   └── routes/          # auth, email, users endpoints
│   ├── db/                  # SQLAlchemy models & session management
│   ├── models/              # DTOs and domain objects
│   │   └── dto.py           # Boundary data transfer objects
│   ├── repos/               # Database access layer
│   ├── services/            # Business logic (sentiment, velocity, stock data)
│   ├── collectors/          # Data collection scripts
│   ├── scripts/             # DB init/seed utilities & migrations
│   └── templates/           # Jinja2 templates for UI
├── jobs/                    # Containerized batch runtime for ECS
│   ├── Dockerfile
│   ├── pyproject.toml       # Separate deps from app
│   ├── ingest/              # Reddit scraper + CLI
│   └── jobs/                # Batch jobs (sentiment, stock prices, daily status)
├── infrastructure/terraform # ECS, ECR, EventBridge, IAM, CloudWatch
├── tests/                   # All tests (unit, integration, regression)
├── docs/                    # Playbooks, migration guides, API docs
├── Makefile                 # Developer + ops automation
├── docker-compose.yml       # Local Postgres + Redis
└── pyproject.toml           # Main app dependencies
```

### Data Flow

```
External Sources                    Processing                      Storage
─────────────────                  ──────────                       ───────
Reddit (PRAW)      ──┐
                     ├──► Collectors ──► Linker ──► Sentiment ──► PostgreSQL
Yahoo Finance      ──┘               (cashtags)   (FinBERT+VADER)    │
                                                                      │
                                     Pipelines ◄──── Repos ◄──────────┘
                                        │
                                        ▼
                                      API ──► Templates ──► Browser
                                        │
                                        └──► JSON ──► Clients
```

### Database Schema (Core Tables)

| Table | Purpose | Key Fields |
|-------|---------|------------|
| `ticker` | Stock universe | `symbol` (PK), `name`, `aliases` (JSONB), `exchange` |
| `article` | Source items | `id` (PK), `url` (UNIQUE), `source`, `title`, `sentiment`, `published_at` |
| `article_ticker` | M:N link | `article_id`, `ticker`, `confidence`, `matched_terms` |
| `reddit_thread` | Discussion tracking | `reddit_id` (PK), `subreddit`, `total_comments`, `is_complete` |
| `scraping_status` | Collector health | `source` (PK), `last_scrape_at`, `items_scraped`, `status` |
| `stock_price` | Current quotes | `symbol` (PK), `price`, `bid`, `ask`, `updated_at` |
| `stock_price_history` | OHLCV series | `id`, `symbol`, `date`, `open`, `high`, `low`, `close`, `volume` |
| `user_profiles` | Auth & prefs | `id`, `email`, `timezone`, `blocked` |

## Development Standards

### Code Style

- **Imports**: stdlib → third-party → local (enforced by ruff)
- **Logging**: `logging.getLogger(__name__)`; structured messages with context
- **State**: No global mutable state; inject dependencies via function parameters or constructors
- **Docstrings**: Module-level and public function boundaries; avoid inline comment noise
- **Functions**: Keep small and pure; prefer composition over inheritance

### NLP & Feature Engineering

| Component | Implementation | Notes |
|-----------|----------------|-------|
| Ticker Linking | Cashtags + symbol dictionary + synonyms; NER fallback | Returns `TickerLinkDTO` with confidence |
| Sentiment | FinBERT (primary) + VADER (fallback) via `HybridSentimentService` | `prob_pos`, `prob_neg`, `prob_neu`, `score` |
| Novelty | `1 - max(cosine similarity)` vs last 24h embeddings per ticker | MiniLM embeddings |
| Velocity | Z-score vs 30-day rolling baseline | Configurable window |
| Signals | `score = w_sent*sent + w_novelty*novelty + w_velocity*velocity + tag_boost` | Weights in config |

### API Design

- Rate limiting via Redis (60 RPM/IP default) with `Retry-After` headers
- Parameter caps enforced centrally and validated in routing layer
- Pydantic request/response models; no raw ORM objects
- Health endpoint: `GET /health` returns `{"status": "ok"}`
- Pagination: `limit`/`offset` with capped maximums

### Batch Jobs

| Job | Schedule | Purpose |
|-----|----------|---------|
| `reddit-scraper` | */15 min | Incremental Reddit ingestion |
| `sentiment-analysis` | */15 min | Process articles lacking sentiment |
| `stock-price-collector` | */15 min (market hours) | Refresh current prices |
| `daily-status` | 04:00 UTC | Aggregate daily metrics |
| `historical-append` | Daily | Append OHLCV history |

### Security

- Gmail-only Google OAuth with JWT sessions
- CSRF-protected state parameters
- No secrets in repository; `.env` locally, AWS Secrets Manager in production
- Bandit security scans in CI (`make security`)

## Governance

### Amendment Process

1. **Propose**: Open a PR modifying this constitution with clear rationale
2. **Review**: At least one maintainer must approve changes to Core Principles
3. **Migrate**: Include migration plan for any breaking changes to existing code
4. **Document**: Update dependent templates if principles change

### Versioning Policy

This constitution follows semantic versioning:

- **MAJOR**: Backward-incompatible governance changes, principle removals, or redefinitions
- **MINOR**: New principle/section added or materially expanded guidance
- **PATCH**: Clarifications, wording improvements, typo fixes

### Compliance Verification

- All PRs MUST verify compliance with Core Principles before merge
- `make lint` and `make test` MUST pass
- Complexity additions require explicit justification in PR description
- Deviations from principles require documented exceptions with expiration dates

### Runtime Guidance

For day-to-day development patterns and practices, consult:
- `.cursor/rules/` for IDE-enforced guidelines
- `docs/TESTING.md` for test strategy details
- `docs/deployment.md` for production deployment procedures
- `Makefile` targets for common operations

**Version**: 1.0.0 | **Ratified**: 2025-12-05 | **Last Amended**: 2025-12-05
