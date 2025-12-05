# Implementation Plan: Weekly Email Digest

**Branch**: `001-weekly-email-digest` | **Date**: 2025-12-05 | **Spec**: [spec.md](./spec.md)  
**Input**: Feature specification from `/specs/001-weekly-email-digest/spec.md`

## Summary

Implement a weekly email digest feature that synthesizes the past week's daily summaries for users who opt into weekly cadence. The system aggregates 7 days of `DailyTickerSummary` records, generates an LLM-powered narrative synthesis highlighting trends, sentiment direction, and top signals, and delivers exactly one weekly email per opted-in user with idempotent tracking.

## Technical Context

**Language/Version**: Python 3.11  
**Primary Dependencies**: FastAPI, SQLAlchemy 2.x, LangChain, boto3 (SES), Pydantic  
**Storage**: PostgreSQL 16 with JSONB support  
**Testing**: pytest with integration tests using real database  
**Target Platform**: Linux server (ECS Fargate)  
**Project Type**: Web application with batch jobs  
**Performance Goals**: Process 10,000 weekly subscribers within 2-hour job window  
**Constraints**: Email rate limit 14/sec via SES, <2hr total job duration  
**Scale/Scope**: Initial rollout to ~1,000 users, scaling to 10,000+

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Layered Architecture | ✅ PASS | Weekly job in `jobs/`, service in `app/services/`, repo in `app/repos/`, API in `app/api/` |
| II. Type Safety | ✅ PASS | All new code will have full type hints; mypy --strict required |
| III. Configuration-Driven | ✅ PASS | Weekly schedule, day/time, batch sizes in `app/config.py` |
| IV. DTO Boundaries | ✅ PASS | New DTOs for weekly digest request/response, cadence preferences |
| V. UTC-First | ✅ PASS | All timestamps UTC; user timezone conversion at render time only |
| VI. Idempotent Operations | ✅ PASS | `WeeklyDigestSendRecord` tracks sent status per user per week |
| VII. Test-Driven | ✅ PASS | Unit tests for services, integration tests for job execution |

**Gate Status**: ✅ PASSED - All principles satisfied

## Project Structure

### Documentation (this feature)

```text
specs/001-weekly-email-digest/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output
│   └── api.yaml         # OpenAPI spec for preference endpoints
└── tasks.md             # Phase 2 output (created by /speckit.tasks)
```

### Source Code (repository root)

```text
app/
├── config.py                          # Add weekly digest config settings
├── db/
│   └── models.py                      # Add WeeklyDigestSendRecord model
├── models/
│   └── dto.py                         # Add weekly digest DTOs
├── repos/
│   ├── summary_repo.py                # Extend for 7-day aggregation
│   └── weekly_digest_repo.py          # NEW: Weekly digest send tracking
├── services/
│   ├── weekly_summary.py              # NEW: Weekly summary aggregation + LLM synthesis
│   ├── email_service.py               # Add send_weekly_digest method
│   ├── email_providers/ses.py         # Implement send_weekly_digest
│   └── email_templates.py             # Add weekly template rendering
├── api/routes/
│   └── users.py                       # Add email cadence preference endpoints
└── templates/email/
    ├── weekly_digest.html             # NEW: Weekly email template
    └── weekly_digest.txt              # NEW: Plain text version

jobs/
└── jobs/
    └── send_weekly_digest.py          # NEW: Weekly digest job CLI

infrastructure/terraform/
├── eventbridge.tf                     # Add weekly digest schedule
└── ecs.tf                             # Add weekly digest task definition

tests/
├── unit/
│   ├── test_weekly_summary.py         # NEW
│   └── test_weekly_digest_repo.py     # NEW
└── integration/
    └── test_weekly_digest_job.py      # NEW
```

**Structure Decision**: Follows existing layered architecture. Weekly digest extends existing daily summary patterns with new service, repo, and job files.

## Complexity Tracking

> No violations - design follows existing patterns with minimal new abstractions.

| Decision | Rationale |
|----------|-----------|
| Use existing `preferences` JSONB on UserProfile | Avoids new table; cadence is a profile preference |
| Separate `WeeklyDigestSendRecord` table | Required for idempotent tracking per user per week |
| Extend `DailyTickerSummaryRepository` | Reuse existing summary queries with date range filter |
