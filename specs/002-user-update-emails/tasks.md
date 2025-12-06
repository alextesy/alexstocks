# Tasks: User Update Emails

**Input**: Design documents from `/specs/002-user-update-emails/`  
**Prerequisites**: plan.md ✅, spec.md ✅, research.md ✅, data-model.md ✅, contracts/ ✅

**Tests**: Tests are included as they are standard practice for critical email operations.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., [US1], [US2], [US3])
- Include exact file paths in descriptions

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Configuration and shared DTOs for update email feature

- [x] T001 Add pyyaml dependency to pyproject.toml for YAML config file parsing
- [x] T002 [P] Add UpdateEmailConfig Pydantic model to app/models/dto.py with fields: subject (str, required, max 200), body_html (str, required), screenshots (list[str], optional), test_mode (bool, required), batch_size (int, optional, default 14, min 1, max 100), batch_delay_seconds (float, optional, default 1.0, min 0.0)
- [x] T003 [P] Add validation methods to UpdateEmailConfig in app/models/dto.py: validate subject (non-empty, trimmed, max 200 chars), validate body_html (non-empty, trimmed), validate screenshots (each path exists and is readable, max 10, image formats PNG/JPG/GIF)

**Checkpoint**: Configuration and DTOs ready for implementation

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core service layer that ALL user stories depend on

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [x] T004 Create UpdateEmailService class in app/services/update_email_service.py with constructor accepting session (Session), email_service (EmailService), user_repo (UserRepository | None)
- [x] T005 Implement get_eligible_users method in app/services/update_email_service.py that returns list[UserDTO] of active, non-deleted users with verified email addresses (excludes bounced emails)
- [x] T006 Implement send_update_email method in app/services/update_email_service.py that accepts config (UpdateEmailConfig), retrieves eligible users (or test user if test_mode), batches sends, handles failures gracefully, returns summary with success/failure counts

**Checkpoint**: Foundation ready - user story implementation can now begin

---

## Phase 3: User Story 1 - Create and Send Ad-Hoc Update Emails (Priority: P1) 🎯 MVP

**Goal**: Enable developers to create and send one-time update emails to all users via Python script with config file

**Independent Test**: Create config file with subject and body_html, set test_mode=true, run script, verify email sent to test user. Then set test_mode=false, run script, verify email sent to all eligible users.

### Tests for User Story 1

> **NOTE: Write these tests FIRST, ensure they FAIL before implementation**

- [x] T007 [P] [US1] Create unit test file tests/unit/test_update_email_service.py with tests for get_eligible_users (returns only active verified users, excludes bounced), send_update_email with test_mode (sends to test user only), send_update_email without test_mode (sends to all eligible users), batch processing (respects batch_size and delay), error handling (continues on individual failures)
- [x] T008 [P] [US1] Create integration test file tests/scripts/test_send_update_email.py with tests for script execution with valid config (sends successfully), script execution with test_mode (sends to test user), script execution without test_mode (sends to all users), config validation errors (exits with error, no emails sent), no eligible users (reports warning, exits successfully)

### Implementation for User Story 1

- [x] T009 [US1] Implement send_update_email.py script in app/scripts/send_update_email.py that accepts config file path as argument, loads and validates config using UpdateEmailConfig, initializes database session and services, calls UpdateEmailService.send_update_email, prints summary report (total recipients, successful, failed)
- [x] T010 [US1] Add config file loading logic in app/scripts/send_update_email.py that supports both YAML and JSON formats, handles file not found errors, validates config structure
- [x] T011 [US1] Add summary reporting in app/scripts/send_update_email.py that prints formatted output showing total recipients, successful sends, failed sends, elapsed time
- [x] T012 [US1] Add error handling in app/scripts/send_update_email.py for config validation errors (exit with clear error message), database connection errors, email service errors (continue and report in summary)
- [x] T013 [US1] Add logging in app/services/update_email_service.py for email send operations (structured logging with user_id, email, status, timestamp)

**Checkpoint**: At this point, User Story 1 should be fully functional and testable independently. Developers can create config files and send update emails to all users or test user.

---

## Phase 4: User Story 2 - Include Screenshots in Update Emails (Priority: P2)

**Goal**: Enable developers to include screenshot images in update emails via file paths in config

**Independent Test**: Create config file with screenshot file paths, run script with test_mode=true, verify email received with images embedded inline in email body.

### Tests for User Story 2

> **NOTE: Write these tests FIRST, ensure they FAIL before implementation**

- [x] T014 [P] [US2] Add unit test in tests/unit/test_update_email_service.py for screenshot handling: validate screenshot file paths exist, validate image formats (PNG/JPG/GIF), reject invalid formats, reject missing files, enforce max 10 screenshots limit
- [x] T015 [P] [US2] Add integration test in tests/scripts/test_send_update_email.py for screenshot embedding: email with screenshots includes images inline, email with invalid screenshot path fails validation, email with too many screenshots fails validation

### Implementation for User Story 2

- [x] T016 [US2] Add screenshot validation method to UpdateEmailConfig in app/models/dto.py that checks file paths exist, validates image formats (PNG, JPG, GIF), enforces max 10 screenshots limit, returns validation errors
- [x] T017 [US2] Implement embed_screenshots method in app/services/update_email_service.py that reads image files from paths, creates MIME multipart email with related subtype, attaches images with Content-ID headers, embeds images in HTML body using cid: references
- [x] T018 [US2] Update send_update_email method in app/services/update_email_service.py to call embed_screenshots when screenshots are provided in config, pass multipart email to email service
- [x] T019 [US2] Add image size validation in app/services/update_email_service.py (recommend max 5MB per image, log warning for large images)

**Checkpoint**: At this point, User Stories 1 AND 2 should both work independently. Developers can include screenshots in update emails.

---

## Phase 5: User Story 3 - Auto-Generate Update Content from Recent Features (Priority: P3)

**Goal**: Automatically generate draft email content from recently implemented features (optional enhancement)

**Independent Test**: Run auto-generation with time range (e.g., last 30 days), verify draft content is generated summarizing recent features, verify content can be edited before sending.

### Tests for User Story 3

> **NOTE: Write these tests FIRST, ensure they FAIL before implementation**

- [x] T020 [P] [US3] Add unit test in tests/unit/test_update_email_service.py for auto-generation: generate_content_from_features with time range returns draft content, generate_content_from_features with no features returns empty content, generate_content_from_features respects time range parameter
- [x] T021 [P] [US3] Add integration test in tests/scripts/test_send_update_email.py for auto-generation: script with auto-generate flag creates draft config file, generated content can be edited, generated content can be used to send email

### Implementation for User Story 3

- [x] T022 [US3] Implement generate_content_from_features method in app/services/update_email_service.py that scans specs/ directory for recent feature implementations (based on git commits or file modification dates), extracts feature summaries from spec.md files, generates draft HTML content summarizing features, returns UpdateEmailConfig with generated content
- [x] T023 [US3] Add --auto-generate flag to send_update_email.py script in app/scripts/send_update_email.py that triggers content generation, writes draft config to file or stdout, allows editing before sending
- [x] T024 [US3] Add time range parameter to generate_content_from_features in app/services/update_email_service.py (default: last 30 days, configurable)

**Checkpoint**: All user stories should now be independently functional. Developers can optionally auto-generate content from recent features.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Improvements that affect multiple user stories

- [x] T025 [P] Add example config files in specs/002-user-update-emails/examples/ with minimal config (test mode), full config (production with screenshots), auto-generated config template
- [x] T026 [P] Update quickstart.md in specs/002-user-update-emails/quickstart.md with actual script usage examples and troubleshooting tips
- [x] T027 Add confirmation prompt in app/scripts/send_update_email.py when test_mode=false to prevent accidental sends to all users (require explicit confirmation)
- [x] T028 Add progress indicator in app/scripts/send_update_email.py for batch processing (show current batch/total batches, estimated time remaining)
- [x] T029 [P] Add HTML email template wrapper option in app/services/update_email_service.py for better email client compatibility (inline CSS, table-based layout)
- [x] T030 Run quickstart.md validation: verify all examples work, update if needed
- [x] T031 [P] Add documentation comments to all public methods in app/services/update_email_service.py and app/scripts/send_update_email.py
- [x] T032 Run linting and formatting: `uv run ruff check --fix .`, `uv run black .`, `uv run mypy .`

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies - can start immediately
- **Foundational (Phase 2)**: Depends on Setup completion (needs UpdateEmailConfig DTO) - BLOCKS all user stories
- **User Story 1 (Phase 3)**: Depends on Foundational completion - Can proceed independently
- **User Story 2 (Phase 4)**: Depends on Foundational completion - Can proceed after US1 or in parallel
- **User Story 3 (Phase 5)**: Depends on Foundational completion - Can proceed after US1 or in parallel
- **Polish (Phase 6)**: Depends on all desired user stories being complete

### User Story Dependencies

| Story | Priority | Depends On | Can Start After |
|-------|----------|------------|-----------------|
| US1   | P1       | Foundational | Phase 2 complete |
| US2   | P2       | Foundational, US1 | US1 complete (builds on email sending) |
| US3   | P3       | Foundational | Phase 2 complete (independent feature) |

### Within Each User Story

1. Tests written first (TDD approach)
2. DTOs/models before services
3. Services before scripts
4. Core implementation before integration
5. Story checkpoint validates independence

### Parallel Opportunities

**Phase 1 (Setup)**: T002, T003 can run in parallel  
**Phase 2 (Foundational)**: Sequential (T005 depends on T004, T006 depends on T005)  
**Phase 3 (US1)**: T007, T008 tests in parallel; T010, T011, T012, T013 can run in parallel after T009  
**Phase 4 (US2)**: T014, T015 tests in parallel; T016, T017, T018, T019 sequential  
**Phase 5 (US3)**: T020, T021 tests in parallel; T022, T023, T024 sequential  
**Phase 6 (Polish)**: T025, T026, T029, T031 can run in parallel

---

## Parallel Example: Phase 3 (US1)

```bash
# Launch all tests for User Story 1 together:
Task T007: "Create unit test file tests/unit/test_update_email_service.py"
Task T008: "Create integration test file tests/scripts/test_send_update_email.py"

# Launch implementation tasks in parallel after T009:
Task T010: "Add config file loading logic"
Task T011: "Add summary reporting"
Task T012: "Add error handling"
Task T013: "Add logging"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup (T001-T003)
2. Complete Phase 2: Foundational (T004-T006)
3. Complete Phase 3: US1 - Create and Send (T007-T013)
4. **STOP and VALIDATE**: Test User Story 1 independently
   - Create test config file
   - Run script with test_mode=true
   - Verify email received
   - Run script with test_mode=false (with confirmation)
   - Verify emails sent to all users
5. Deploy/demo if ready

### Incremental Delivery

| Milestone | Stories Complete | Value Delivered |
|-----------|------------------|-----------------|
| MVP       | US1              | Developers can send update emails |
| Enhanced  | US1 + US2        | Update emails with screenshots |
| Complete  | US1 + US2 + US3  | Auto-generation convenience feature |

### Suggested Team Allocation

**Single Developer**:
1. Setup → Foundational → US1 → US2 → US3 → Polish

**Two Developers**:
- Dev A: Setup → Foundational → US1 → US2
- Dev B: (wait for Foundational) → US3 → Polish

---

## Task Summary

| Phase | Tasks | Parallelizable | Story |
|-------|-------|----------------|-------|
| Setup | 3 | 2 | - |
| Foundational | 3 | 0 | - |
| US1 (P1) | 7 | 2 tests, 4 impl | Create and Send |
| US2 (P2) | 6 | 2 tests | Screenshots |
| US3 (P3) | 5 | 2 tests | Auto-Generate |
| Polish | 8 | 4 | - |
| **Total** | **32** | **12** | - |

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- Each user story should be independently completable and testable
- Verify tests fail before implementing
- Commit after each task or logical group
- Stop at any checkpoint to validate story independently
- US2 builds on US1 (screenshot embedding extends email sending)
- US3 is independent (can be implemented separately)
- Always test with test_mode=true before production sends

