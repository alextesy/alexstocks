# Tasks: Weekly Email Digest

**Input**: Design documents from `/specs/001-weekly-email-digest/`  
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/api.yaml

**Tests**: Included as per Constitution Principle VII (Test-Driven Confidence)

**Organization**: Tasks grouped by user story for independent implementation and testing

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1-US5)
- Paths relative to repository root

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Configuration and shared DTOs for weekly digest feature

- [x] T001 Add weekly digest configuration settings in app/config.py
- [x] T002 [P] Add EmailCadence enum to app/models/dto.py
- [x] T003 [P] Add WeeklyDigestContent dataclass to app/models/dto.py
- [x] T004 [P] Add WeeklyTickerAggregate dataclass to app/models/dto.py
- [x] T005 [P] Add WeeklyDigestSendRecordDTO to app/models/dto.py

**Checkpoint**: Configuration and DTOs ready for implementation

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Database model and repository that ALL user stories depend on

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [x] T006 Add WeeklyDigestSendRecord model to app/db/models.py
- [x] T007 Create database migration for weekly_digest_send_record table in app/scripts/migrations/
- [x] T008 Create WeeklyDigestRepository in app/repos/weekly_digest_repo.py
- [x] T009 [P] Extend DailyTickerSummaryRepository with get_summaries_for_week method in app/repos/summary_repo.py
- [x] T010 [P] Add indexes to app/db/models.py for WeeklyDigestSendRecord

**Checkpoint**: Foundation ready - user story implementation can now begin

---

## Phase 3: User Story 1 - Subscribe to Weekly Digest (Priority: P1) 🎯 MVP

**Goal**: Users can select email cadence preference (daily only, weekly only, or both)

**Independent Test**: User changes preference from daily to weekly, preference persists across sessions

### Tests for User Story 1

- [x] T011 [P] [US1] Unit test for email cadence preference in tests/unit/test_email_cadence.py
- [x] T012 [P] [US1] Integration test for cadence API endpoints in tests/integration/test_email_cadence_api.py

### Implementation for User Story 1

- [x] T013 [US1] Update UserProfileUpdateDTO with email_cadence field in app/models/dto.py
- [x] T014 [US1] Add get_email_cadence helper method to UserRepository in app/repos/user_repo.py
- [x] T015 [US1] Add update_email_cadence method to UserRepository in app/repos/user_repo.py
- [x] T016 [US1] Implement GET /api/users/me/email-cadence endpoint in app/api/routes/users.py
- [x] T017 [US1] Implement PUT /api/users/me/email-cadence endpoint in app/api/routes/users.py
- [x] T018 [US1] Add email cadence validation (daily_only, weekly_only, both) in app/api/routes/users.py
- [x] T019 [US1] Update existing daily email logic to respect cadence preference in app/services/email_dispatch_service.py

**Checkpoint**: Users can opt-in/out of weekly digest. US1 independently testable.

---

## Phase 4: User Story 2 - Receive Weekly Digest Email (Priority: P1) 🎯 MVP

**Goal**: Opted-in users receive synthesized weekly email summarizing past week's activity

**Independent Test**: Trigger weekly job for user with daily summaries, verify email received with correct structure

### Tests for User Story 2

- [x] T020 [P] [US2] Unit test for WeeklySummaryService in tests/unit/test_weekly_summary.py
- [x] T021 [P] [US2] Unit test for weekly email template rendering in tests/unit/test_weekly_email_template.py
- [x] T022 [P] [US2] Integration test for weekly digest job in tests/integration/test_weekly_digest_job.py

### Implementation for User Story 2

- [x] T023 [P] [US2] Create weekly digest HTML email template in app/templates/email/weekly_digest.html
- [x] T024 [P] [US2] Create weekly digest plain text email template in app/templates/email/weekly_digest.txt
- [x] T025 [US2] Implement WeeklySummaryService with aggregate_weekly_summaries method in app/services/weekly_summary.py
- [x] T026 [US2] Add LLM prompt for weekly synthesis in app/services/weekly_summary.py
- [x] T027 [US2] Add render_weekly_digest method to EmailTemplateService in app/services/email_templates.py
- [x] T028 [US2] Add send_weekly_digest abstract method to EmailService base class in app/services/email_service.py
- [x] T029 [US2] Implement send_weekly_digest in SESEmailService in app/services/email_providers/ses.py
- [x] T030 [US2] Create WeeklyDigestDispatchService in app/services/weekly_digest_dispatch.py
- [x] T031 [US2] Create weekly digest job CLI in jobs/jobs/send_weekly_digest.py
- [x] T032 [US2] Add --dry-run and --user-email flags to weekly digest job CLI

**Checkpoint**: Weekly digest emails can be generated and sent. US2 independently testable.

---

## Phase 5: User Story 3 - Weekly Digest Content Quality (Priority: P2)

**Goal**: Weekly digest synthesizes themes into cohesive narrative with all required sections

**Independent Test**: Review generated content for: headline, 3-5 bullets, sentiment direction, no day-by-day repetition

### Tests for User Story 3

- [x] T033 [P] [US3] Unit test for LLM response parsing in tests/unit/test_weekly_summary.py
- [x] T034 [P] [US3] Unit test for sentiment trend calculation in tests/unit/test_weekly_summary.py

### Implementation for User Story 3

- [x] T035 [US3] Add structured output schema (WeeklySummaryInfo) to app/services/weekly_summary.py
- [x] T036 [US3] Implement sentiment_trend calculation (improving/stable/declining) in app/services/weekly_summary.py
- [x] T037 [US3] Add limited data acknowledgment logic in app/services/weekly_summary.py
- [x] T038 [US3] Refine LLM prompt for synthesis vs repetition in app/services/weekly_summary.py
- [x] T039 [US3] Add TopSignal extraction logic in app/services/weekly_summary.py
- [x] T040 [US3] Add recommended next actions generation in app/services/weekly_summary.py

**Checkpoint**: Weekly digest content meets quality criteria. US3 independently testable.

---

## Phase 6: User Story 4 - Idempotent Weekly Delivery (Priority: P2)

**Goal**: Exactly one email per user per week, even with retries or partial failures

**Independent Test**: Run job twice for same user in same week, verify only one email sent

### Tests for User Story 4

- [x] T041 [P] [US4] Unit test for idempotency check in tests/unit/test_weekly_digest_repo.py
- [x] T042 [P] [US4] Integration test for retry logic in tests/integration/test_weekly_digest_job.py

### Implementation for User Story 4

- [x] T043 [US4] Add check_already_sent method to WeeklyDigestRepository in app/repos/weekly_digest_repo.py
- [x] T044 [US4] Add mark_sent and mark_failed methods to WeeklyDigestRepository in app/repos/weekly_digest_repo.py
- [x] T045 [US4] Add mark_skipped method with skip_reason to WeeklyDigestRepository in app/repos/weekly_digest_repo.py
- [x] T046 [US4] Implement idempotency check in WeeklyDigestDispatchService in app/services/weekly_digest_dispatch.py
- [x] T047 [US4] Add per-user error handling (continue on failure) in app/services/weekly_digest_dispatch.py
- [x] T048 [US4] Add comprehensive job run logging in jobs/jobs/send_weekly_digest.py
- [x] T049 [US4] Add GET /api/users/me/weekly-digest/history endpoint in app/api/routes/users.py

**Checkpoint**: Idempotent delivery guaranteed. US4 independently testable.

---

## Phase 7: User Story 5 - Weekly Job Scheduling (Priority: P3)

**Goal**: Job runs automatically on schedule, deployed via CI/CD

**Independent Test**: Verify EventBridge schedule triggers ECS task at configured time

### Tests for User Story 5

- [ ] T050 [P] [US5] Validate Terraform plan for weekly digest resources

### Implementation for User Story 5

- [x] T051 [P] [US5] Add CloudWatch log group for weekly-digest in infrastructure/terraform/ecs.tf
- [x] T052 [P] [US5] Add DLQ for weekly digest job in infrastructure/terraform/eventbridge.tf
- [x] T053 [US5] Add ECS task definition for weekly-digest in infrastructure/terraform/ecs.tf
- [x] T054 [US5] Add EventBridge schedule for weekly digest (Sunday 9:00 UTC) in infrastructure/terraform/eventbridge.tf
- [x] T055 [US5] Add weekly digest task to deploy-ecs-jobs.yml update_task_definition calls in .github/workflows/deploy-ecs-jobs.yml
- [x] T056 [US5] Add weekly digest log group import in deploy-ecs-jobs.yml in .github/workflows/deploy-ecs-jobs.yml
- [x] T057 [US5] Add weekly digest to EventBridge import in deploy-ecs-jobs.yml in .github/workflows/deploy-ecs-jobs.yml
- [x] T058 [US5] Add weekly digest logs link to deployment summary in .github/workflows/deploy-ecs-jobs.yml

**Checkpoint**: Job scheduled and deployed via CI/CD. US5 independently testable.

---

## Phase 8: Polish & Cross-Cutting Concerns

**Purpose**: Admin endpoints, documentation, final validation

- [ ] T059 [P] Implement POST /api/admin/weekly-digest/trigger endpoint in app/api/routes/admin.py
- [ ] T060 [P] Implement GET /api/admin/weekly-digest/stats endpoint in app/api/routes/admin.py
- [ ] T061 [P] Update quickstart.md with actual CLI commands and test results in specs/001-weekly-email-digest/quickstart.md
- [x] T062 Run ruff check --fix, black, and mypy on all new files
- [ ] T063 Validate all acceptance scenarios from spec.md pass
- [x] T064 Run full test suite and verify all tests pass

---

## Dependencies & Execution Order

### Phase Dependencies

```
Phase 1: Setup ──────────────────────────────────────────────┐
                                                              │
Phase 2: Foundational ◄──────────────────────────────────────┘
    │
    ├──► Phase 3: US1 (Subscribe) ──► Can proceed independently
    │
    ├──► Phase 4: US2 (Receive) ────► Depends on US1 for cadence check
    │
    ├──► Phase 5: US3 (Quality) ────► Depends on US2 for content generation
    │
    ├──► Phase 6: US4 (Idempotent) ─► Can proceed after Foundational
    │
    └──► Phase 7: US5 (Scheduling) ─► Depends on US2 job existing
                                              │
Phase 8: Polish ◄─────────────────────────────┘
```

### User Story Dependencies

| Story | Priority | Depends On | Can Start After |
|-------|----------|------------|-----------------|
| US1   | P1       | None       | Phase 2 complete |
| US2   | P1       | US1        | US1 complete (needs cadence check) |
| US3   | P2       | US2        | US2 complete (refines content) |
| US4   | P2       | None       | Phase 2 complete |
| US5   | P3       | US2        | US2 complete (deploys the job) |

### Within Each User Story

1. Tests written first (TDD approach)
2. Models/DTOs before services
3. Services before API endpoints
4. Core implementation before integration
5. Story checkpoint validates independence

### Parallel Opportunities

**Phase 1 (Setup)**: T002, T003, T004, T005 can run in parallel  
**Phase 2 (Foundational)**: T009, T010 can run in parallel after T006  
**Phase 3 (US1)**: T011, T012 tests in parallel; T016, T017 endpoints in parallel  
**Phase 4 (US2)**: T020-T022 tests in parallel; T023, T024 templates in parallel  
**Phase 5 (US3)**: T033, T034 tests in parallel  
**Phase 6 (US4)**: T041, T042 tests in parallel  
**Phase 7 (US5)**: T051, T052 infrastructure in parallel  
**Phase 8 (Polish)**: T059, T060, T061 can run in parallel

---

## Parallel Example: Phase 4 (US2)

```bash
# Launch tests in parallel:
Task T020: "Unit test for WeeklySummaryService"
Task T021: "Unit test for weekly email template rendering"
Task T022: "Integration test for weekly digest job"

# Launch templates in parallel:
Task T023: "Create weekly digest HTML email template"
Task T024: "Create weekly digest plain text email template"
```

---

## Implementation Strategy

### MVP First (US1 + US2)

1. Complete Phase 1: Setup (T001-T005)
2. Complete Phase 2: Foundational (T006-T010)
3. Complete Phase 3: US1 - Subscribe (T011-T019)
4. **VALIDATE**: Test cadence preference works independently
5. Complete Phase 4: US2 - Receive (T020-T032)
6. **VALIDATE**: Run dry-run job, verify email generation
7. **MVP READY**: Users can opt-in and receive weekly digests

### Incremental Delivery

| Milestone | Stories Complete | Value Delivered |
|-----------|------------------|-----------------|
| MVP       | US1 + US2        | Users receive weekly digests |
| Quality   | + US3            | Better content synthesis |
| Reliable  | + US4            | No duplicates, retry-safe |
| Production| + US5            | Automated scheduling |

### Suggested Team Allocation

**Single Developer**:
1. Setup → Foundational → US1 → US2 → US4 → US3 → US5 → Polish

**Two Developers**:
- Dev A: Setup → Foundational → US1 → US2 → US3
- Dev B: (wait for Foundational) → US4 → US5 → Polish

---

## Task Summary

| Phase | Tasks | Parallelizable | Story |
|-------|-------|----------------|-------|
| Setup | 5 | 4 | - |
| Foundational | 5 | 2 | - |
| US1 (P1) | 9 | 2 tests, 2 endpoints | Subscribe |
| US2 (P1) | 13 | 3 tests, 2 templates | Receive |
| US3 (P2) | 8 | 2 tests | Quality |
| US4 (P2) | 9 | 2 tests | Idempotent |
| US5 (P3) | 9 | 3 infra | Scheduling |
| Polish | 6 | 3 | - |
| **Total** | **64** | **21** | - |

---

## Notes

- Tasks marked [P] can run in parallel within their phase
- Each user story has a checkpoint for independent validation
- MVP = US1 + US2 (users can subscribe and receive emails)
- US4 (idempotency) should be prioritized early for production safety
- US5 (scheduling) is last as job can be manually triggered initially
- Run `uv run ruff check --fix . && uv run black . && uv run mypy .` after each phase

