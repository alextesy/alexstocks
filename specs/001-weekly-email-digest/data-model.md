# Data Model: Weekly Email Digest

**Feature**: 001-weekly-email-digest  
**Date**: 2025-12-05

## Entity Overview

```
┌─────────────────┐     ┌──────────────────────────┐
│     User        │────<│  WeeklyDigestSendRecord  │
└─────────────────┘     └──────────────────────────┘
        │                           │
        │                           │ references
        v                           v
┌─────────────────┐     ┌──────────────────────────┐
│  UserProfile    │     │   DailyTickerSummary     │
│  (preferences)  │     │   (aggregated input)     │
└─────────────────┘     └──────────────────────────┘
```

## New Entity: WeeklyDigestSendRecord

Tracks weekly digest send status per user per week for idempotent delivery.

### Fields

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `id` | BIGINT | PK, AUTO | Primary key |
| `user_id` | BIGINT | FK→users.id, NOT NULL | User receiving the digest |
| `week_start_date` | DATE | NOT NULL | Monday of the ISO week (UTC) |
| `status` | VARCHAR(20) | NOT NULL, DEFAULT 'pending' | pending, sent, failed, skipped |
| `ticker_count` | INT | NOT NULL, DEFAULT 0 | Number of tickers in digest |
| `days_with_data` | INT | NOT NULL, DEFAULT 0 | Days with summaries (0-7) |
| `message_id` | VARCHAR(255) | NULLABLE | SES message ID if sent |
| `error` | TEXT | NULLABLE | Error message if failed |
| `skip_reason` | VARCHAR(100) | NULLABLE | Reason if skipped (e.g., 'no_summaries') |
| `created_at` | TIMESTAMPTZ | NOT NULL, DEFAULT NOW() | Record creation time |
| `sent_at` | TIMESTAMPTZ | NULLABLE | Actual send time |

### Constraints

```sql
UNIQUE(user_id, week_start_date)  -- Idempotency guarantee
INDEX(week_start_date, status)    -- Job query optimization
INDEX(user_id)                    -- User history lookup
```

### State Transitions

```
                    ┌─────────┐
      job starts    │ pending │
          │         └────┬────┘
          │              │
          ▼              │
    check existing? ─────┘
          │
          │ no existing record
          │
          ▼
    ┌─────────────┐
    │ check data  │
    └──────┬──────┘
           │
     ┌─────┴─────┐
     │           │
     │ no data   │ has data
     │           │
     ▼           ▼
┌─────────┐  ┌─────────┐
│ skipped │  │  send   │
└─────────┘  └────┬────┘
                  │
            ┌─────┴─────┐
            │           │
            │ success   │ failure
            │           │
            ▼           ▼
       ┌────────┐  ┌────────┐
       │  sent  │  │ failed │
       └────────┘  └────────┘
```

### SQLAlchemy Model

```python
class WeeklyDigestSendRecord(Base):
    """Track weekly digest send status per user per week."""

    __tablename__ = "weekly_digest_send_record"

    id: Mapped[int] = mapped_column(
        BigIntegerCompat, primary_key=True, autoincrement=True
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    week_start_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending"
    )  # pending, sent, failed, skipped
    ticker_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    days_with_data: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    message_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    skip_reason: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
    sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Relationships
    user: Mapped["User"] = relationship("User")

    __table_args__ = (
        UniqueConstraint("user_id", "week_start_date", name="uq_weekly_digest_user_week"),
        Index("ix_weekly_digest_week_status", "week_start_date", "status"),
        Index("ix_weekly_digest_user", "user_id"),
    )
```

---

## Modified Entity: UserProfile

Extended to include email cadence preference in existing `preferences` JSONB field.

### Updated Preferences Schema

```python
# UserProfile.preferences JSONB structure:
{
    # Existing fields
    "notify_on_surges": bool,          # default: True
    "notify_on_most_discussed": bool,  # default: True
    "notify_on_daily_briefing": bool,  # default: True
    
    # NEW: Email cadence preference
    "email_cadence": str,  # "daily_only" | "weekly_only" | "both"
                           # default: "both" for new users
                           # backward compat: treat null/missing as "daily_only"
}
```

### Validation Rules

| Field | Valid Values | Default | Notes |
|-------|--------------|---------|-------|
| `email_cadence` | `daily_only`, `weekly_only`, `both` | `both` | For new users |
| `email_cadence` | null/missing | treated as `daily_only` | Backward compat for existing users |

### DTO Update

```python
class EmailCadence(str, Enum):
    """Email delivery cadence options."""
    DAILY_ONLY = "daily_only"
    WEEKLY_ONLY = "weekly_only"
    BOTH = "both"

@dataclass
class UserProfileUpdateDTO:
    """DTO for updating user profile."""
    
    # Existing fields...
    nickname: str | None = None
    timezone: str | None = None
    notification_defaults: dict | None = None
    
    # NEW
    email_cadence: EmailCadence | None = None
```

---

## Aggregated View: WeeklyTickerAggregate

Not a database entity - computed view for weekly digest generation.

### Structure

```python
@dataclass(frozen=True)
class WeeklyTickerAggregate:
    """Aggregated ticker data for weekly digest."""
    
    ticker: str
    ticker_name: str
    
    # Aggregated metrics
    total_mentions: int
    total_engagement: int
    days_with_data: int
    
    # Sentiment analysis
    avg_sentiment: float | None
    sentiment_trend: str  # "improving", "stable", "declining"
    sentiment_start: float | None  # First day's sentiment
    sentiment_end: float | None    # Last day's sentiment
    
    # Daily summaries for LLM synthesis
    daily_summaries: list[str]       # Ordered by date
    daily_sentiments: list[str]      # LLM sentiment categories
    daily_bullets: list[list[str]]   # Bullet points per day
```

### Derivation Rules

| Field | Calculation |
|-------|-------------|
| `total_mentions` | `SUM(mention_count)` for ticker in 7-day window |
| `avg_sentiment` | `AVG(avg_sentiment)` for ticker in window |
| `sentiment_trend` | Compare first half avg vs second half avg: >0.1 diff = improving/declining |
| `days_with_data` | `COUNT(DISTINCT summary_date)` for ticker |

---

## Weekly Digest Content Structure

Output of LLM synthesis for email rendering.

```python
@dataclass
class WeeklyDigestContent:
    """Structured content for weekly digest email."""
    
    # Metadata
    week_start: date
    week_end: date
    user_timezone: str
    generated_at: datetime
    
    # Content sections
    headline: str                     # 1 sentence summary
    highlights: list[str]             # 3-5 bullet points
    top_signals: list[TopSignal]      # Theme + examples
    sentiment_direction: SentimentDirection
    risks_opportunities: list[str]    # Key patterns
    next_actions: list[str]           # 2-3 recommendations
    
    # Per-ticker summaries (abbreviated)
    ticker_summaries: list[WeeklyTickerSummaryBrief]


@dataclass
class TopSignal:
    """Top signal/theme from the week."""
    theme: str
    examples: list[str]
    tickers_involved: list[str]


@dataclass
class SentimentDirection:
    """Sentiment trend analysis."""
    direction: str  # "improving", "stable", "declining"
    evidence: str   # Supporting text
    confidence: float  # 0.0-1.0


@dataclass
class WeeklyTickerSummaryBrief:
    """Brief ticker summary for email."""
    ticker: str
    ticker_name: str
    sentiment_emoji: str  # 🚀, 📈, ➡️, 📉, 💀
    one_liner: str
    mention_count: int
```

---

## Relationships

```
User (1) ──────────────< (N) WeeklyDigestSendRecord
  │
  └─── (1) UserProfile
            │
            └─── preferences.email_cadence
            
User (1) ──────────────< (N) UserTickerFollow
                               │
                               └─── ticker ──> DailyTickerSummary (aggregated)
```

---

## Migration Strategy

### Phase 1: Schema Migration

```sql
-- Add WeeklyDigestSendRecord table
CREATE TABLE weekly_digest_send_record (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    week_start_date DATE NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    ticker_count INT NOT NULL DEFAULT 0,
    days_with_data INT NOT NULL DEFAULT 0,
    message_id VARCHAR(255),
    error TEXT,
    skip_reason VARCHAR(100),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    sent_at TIMESTAMPTZ,
    CONSTRAINT uq_weekly_digest_user_week UNIQUE (user_id, week_start_date)
);

CREATE INDEX ix_weekly_digest_week_status ON weekly_digest_send_record(week_start_date, status);
CREATE INDEX ix_weekly_digest_user ON weekly_digest_send_record(user_id);
```

### Phase 2: Data Migration (Optional Backfill)

```sql
-- Set default email_cadence for existing users (optional)
-- By default, null/missing is treated as 'daily_only' in code
-- This migration explicitly sets it if desired:

UPDATE user_profiles
SET preferences = COALESCE(preferences, '{}'::jsonb) || '{"email_cadence": "daily_only"}'::jsonb
WHERE preferences IS NULL 
   OR NOT (preferences ? 'email_cadence');
```

---

## Query Patterns

### Get users eligible for weekly digest

```sql
SELECT u.id, u.email, up.timezone, up.preferences
FROM users u
JOIN user_profiles up ON up.user_id = u.id
WHERE u.is_active = true
  AND u.is_deleted = false
  AND (
    up.preferences->>'email_cadence' = 'weekly_only'
    OR up.preferences->>'email_cadence' = 'both'
  )
  AND NOT EXISTS (
    SELECT 1 FROM weekly_digest_send_record wd
    WHERE wd.user_id = u.id
      AND wd.week_start_date = :week_start
      AND wd.status IN ('sent', 'skipped')
  );
```

### Aggregate daily summaries for user's watchlist

```sql
SELECT 
    dts.ticker,
    t.name as ticker_name,
    SUM(dts.mention_count) as total_mentions,
    SUM(dts.engagement_count) as total_engagement,
    AVG(dts.avg_sentiment) as avg_sentiment,
    COUNT(DISTINCT dts.summary_date) as days_with_data,
    ARRAY_AGG(dts.llm_summary ORDER BY dts.summary_date) as daily_summaries,
    ARRAY_AGG(dts.llm_sentiment ORDER BY dts.summary_date) as daily_sentiments
FROM daily_ticker_summary dts
JOIN ticker t ON t.symbol = dts.ticker
WHERE dts.summary_date >= :week_start
  AND dts.summary_date < :week_end
  AND dts.ticker IN (
    SELECT utf.ticker 
    FROM user_ticker_follows utf 
    WHERE utf.user_id = :user_id
  )
GROUP BY dts.ticker, t.name
ORDER BY total_mentions DESC;
```

