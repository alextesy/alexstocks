# Research: Weekly Email Digest

**Feature**: 001-weekly-email-digest  
**Date**: 2025-12-05

## Research Questions & Findings

### 1. How should email cadence preference be stored?

**Decision**: Use existing `preferences` JSONB column on `UserProfile` model

**Rationale**:
- `UserProfile.preferences` is already a JSONB field designed for flexible user settings
- Avoids schema migration for a new column
- Consistent with existing notification_defaults pattern in `UserProfileDTO`
- Allows easy addition of future preference options

**Alternatives Considered**:
- New `email_cadence` enum column on `UserProfile`: Rejected - requires migration, less flexible
- Separate `UserEmailPreference` table: Rejected - over-engineering for a single preference field
- `UserNotificationChannel.preferences` field: Rejected - that's for channel-specific settings, not cadence

**Implementation**:
```python
# In UserProfile.preferences JSONB:
{
    "email_cadence": "daily_only" | "weekly_only" | "both",
    # existing fields preserved
    "notify_on_surges": true,
    "notify_on_most_discussed": true,
    ...
}
```

Default: `"both"` for new users, `"daily_only"` for existing users (backward compatible)

---

### 2. How to track idempotent weekly sends?

**Decision**: New `WeeklyDigestSendRecord` table

**Rationale**:
- `EmailSendLog` tracks daily sends by `summary_date` - not designed for weekly windows
- Need unique constraint on `(user_id, week_start_date)` for idempotency
- Must track status independently from daily sends for retry logic
- Mirrors existing pattern but adapted for weekly granularity

**Alternatives Considered**:
- Extend `EmailSendLog` with `digest_type` column: Rejected - breaks existing queries, different semantics
- Use `summary_date` with special marker: Rejected - hacky, poor data modeling
- Redis-based tracking: Rejected - not durable, inconsistent with existing patterns

**Schema**:
```sql
CREATE TABLE weekly_digest_send_record (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT REFERENCES users(id) ON DELETE CASCADE NOT NULL,
    week_start_date DATE NOT NULL,  -- Monday of the week (ISO week)
    status VARCHAR(20) NOT NULL DEFAULT 'pending',  -- pending, sent, failed, skipped
    ticker_count INT NOT NULL DEFAULT 0,
    message_id VARCHAR(255),
    error TEXT,
    skip_reason VARCHAR(100),  -- 'no_summaries', 'user_opted_out', etc.
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    sent_at TIMESTAMPTZ,
    UNIQUE(user_id, week_start_date)
);
```

---

### 3. How to aggregate daily summaries for weekly digest?

**Decision**: Query `DailyTickerSummary` for 7-day window, group by ticker, synthesize with LLM

**Rationale**:
- Existing `DailyTickerSummary` already contains LLM-generated summaries per ticker per day
- Aggregation can compute: total mentions, average sentiment across week, sentiment trend
- LLM synthesis generates narrative from daily summaries (not raw articles)
- Follows existing pattern of `DailySummaryService` but at weekly granularity

**Implementation**:
```python
# Aggregate query for 7-day window:
SELECT 
    ticker,
    SUM(mention_count) as total_mentions,
    AVG(avg_sentiment) as avg_sentiment_week,
    MIN(summary_date) as first_day_with_data,
    MAX(summary_date) as last_day_with_data,
    COUNT(*) as days_with_data,
    ARRAY_AGG(llm_summary ORDER BY summary_date) as daily_summaries,
    ARRAY_AGG(llm_sentiment ORDER BY summary_date) as daily_sentiments
FROM daily_ticker_summary
WHERE summary_date >= :week_start AND summary_date < :week_end
  AND ticker IN (SELECT ticker FROM user_ticker_follows WHERE user_id = :user_id)
GROUP BY ticker
ORDER BY total_mentions DESC;
```

---

### 4. What LLM prompt pattern for weekly synthesis?

**Decision**: Build on existing `DailySummaryService` prompt pattern with weekly-specific instructions

**Rationale**:
- Existing prompt in `build_prompt_for_ticker()` works well for sentiment classification
- Weekly prompt should synthesize daily summaries, not re-analyze raw articles
- Focus on trend identification, not day-by-day repetition
- Output structure matches spec: headline, bullets, sentiment direction, next actions

**Prompt Structure**:
```text
You are an expert financial analyst synthesizing a week's worth of market sentiment data 
for a personalized weekly digest email.

CONTEXT:
- User's watchlist: {tickers}
- Week: {week_start} to {week_end}
- Daily summaries attached below

TASK:
Synthesize the daily summaries into a cohesive weekly narrative. Do NOT repeat 
day-by-day information. Instead:

1. HEADLINE (1 sentence): Most significant market sentiment theme of the week
2. KEY HIGHLIGHTS (3-5 bullets): Major trends, surprises, or noteworthy signals
3. SENTIMENT DIRECTION: Is overall sentiment improving, stable, or declining? 
   Cite specific evidence from the sentiment scores.
4. TOP SIGNALS: Most discussed themes or catalysts across all tickers
5. RISKS/OPPORTUNITIES: Emerging patterns that warrant attention
6. RECOMMENDED NEXT ACTIONS (2-3 bullets): Suggested focus areas for next week

OUTPUT FORMAT: Structured JSON with sections as keys.
```

---

### 5. What job scheduling approach for weekly digest?

**Decision**: AWS EventBridge Scheduler with ECS Fargate task, similar to existing `daily_status` job

**Rationale**:
- Existing pattern proven for `daily_status`, `stock_price_collector`, `send_daily_emails`
- EventBridge supports cron expressions with timezone awareness
- ECS Fargate Spot for cost efficiency (same as other batch jobs)
- DLQ for failed job tracking

**Schedule Configuration**:
```hcl
# Sunday 9:00 AM UTC (configurable)
schedule_expression = "cron(0 9 ? * SUN *)"
schedule_expression_timezone = "UTC"
```

**User Timezone Handling**:
- Job runs at single time (UTC-based)
- All users processed in same run
- Email "sent time" logged in UTC
- User timezone used only for email content display (e.g., "Week of Dec 1-7")

---

### 6. How to handle DST transitions?

**Decision**: Use UTC for all job scheduling; timezone-aware datetime for user display only

**Rationale**:
- Constitution Principle V mandates UTC-first
- EventBridge uses UTC by default; no DST issues in job scheduling
- User timezone (from `UserProfile.timezone`) used only in email template rendering
- Existing `ZoneInfo` usage in `daily_summary.py` provides pattern

**Implementation**:
- `week_start_date` stored as UTC date
- Email template converts to user timezone for display: "Week of November 25 - December 1"
- Job cutoff is UTC midnight Sunday; late data rolls to next week

---

### 7. Rate limiting and batch processing strategy?

**Decision**: Batch processing with 14 emails/sec rate limit, matching existing daily email pattern

**Rationale**:
- Existing `EmailDispatchService.send_batch()` uses `rate_limit_delay = 1.0 / 14.0`
- SES rate limit is typically 14/sec in production
- 10,000 users × (1/14) sec = ~12 minutes for full batch
- Well within 2-hour job window requirement

**Batch Processing Flow**:
1. Query all users with `email_cadence` in `['weekly_only', 'both']`
2. For each user, check `WeeklyDigestSendRecord` for idempotency
3. Skip if already sent this week
4. Aggregate daily summaries for user's watchlist
5. Skip if no summaries exist (log reason)
6. Generate weekly digest content via LLM
7. Render email template
8. Send via SES with retry
9. Record success/failure in `WeeklyDigestSendRecord`

---

### 8. How to define "week" boundaries?

**Decision**: ISO week (Monday-Sunday) with cutoff at job run time

**Rationale**:
- ISO 8601 week definition is unambiguous
- Most business contexts use Monday as week start
- `week_start_date` is the Monday of the ISO week
- Data window: Monday 00:00 UTC to Sunday 23:59:59 UTC (or job start time if earlier)

**Implementation**:
```python
from datetime import datetime, timedelta

def get_iso_week_start(dt: datetime) -> date:
    """Return Monday of the ISO week containing dt."""
    return (dt - timedelta(days=dt.weekday())).date()

# Example: Job runs Sunday Dec 8 at 09:00 UTC
# week_start = Monday Dec 2
# Data window: Dec 2 00:00 UTC to Dec 8 09:00 UTC (job start)
```

---

## Dependencies Verified

| Dependency | Status | Notes |
|------------|--------|-------|
| `DailyTickerSummary` table | ✅ Exists | Has `llm_summary`, `llm_sentiment`, `avg_sentiment` |
| `UserProfile.preferences` | ✅ Exists | JSONB field for user settings |
| `EmailService.send_email()` | ✅ Exists | Generic email sending method |
| `EmailTemplateService` | ✅ Exists | Jinja2 template rendering |
| `LangChain` integration | ✅ Exists | Used by `DailySummaryService` |
| EventBridge scheduler | ✅ Exists | Pattern in `eventbridge.tf` |
| ECS task definitions | ✅ Exists | Pattern in `ecs.tf` |

---

## Open Questions Resolved

All technical questions resolved. Implementation can proceed with:
1. Database migration for `WeeklyDigestSendRecord` table
2. Service layer for weekly summary aggregation and LLM synthesis
3. Email template for weekly digest
4. Job CLI for scheduled execution
5. API endpoints for cadence preference management
6. Terraform resources for scheduling

