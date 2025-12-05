# Tasks: Delete User Account

**Input**: Design documents from `/specs/001-delete-user/`  
**Prerequisites**: plan.md ✅, spec.md ✅, research.md ✅, data-model.md ✅, contracts/ ✅

**Tests**: Tests are included as they are standard practice for critical user operations like account deletion.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., [US1], [US2])
- Include exact file paths in descriptions

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: No new infrastructure needed - leveraging existing codebase structure

**Note**: This feature builds on existing infrastructure. No setup tasks required as all dependencies (database, authentication, Slack service) already exist.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core components that MUST be complete before user stories can be implemented

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [x] T001 [P] Create UserDeletionResponseDTO in app/models/dto.py with success (bool) and message (str) fields
- [x] T002 [P] Add notify_user_deleted method to SlackService in app/services/slack_service.py following notify_user_created pattern, sending to market-pulse-users channel with user_id, email, timestamp, and environment

**Checkpoint**: Foundation ready - user story implementation can now begin

---

## Phase 3: User Story 1 - Delete Account from Settings (Priority: P1) 🎯 MVP

**Goal**: Enable users to permanently delete their account and all associated data from the settings page with confirmation dialog

**Independent Test**: Navigate to settings, click delete account, confirm deletion, verify all user data removed from database, sign in again and verify fresh account created

### Tests for User Story 1

> **NOTE: Write these tests FIRST, ensure they FAIL before implementation**

- [x] T003 [P] [US1] Create unit test file tests/test_user_deletion_service.py with tests for successful deletion, user not found, database error rollback, Slack notification failure handling, and audit logging
- [x] T004 [P] [US1] Create integration test file tests/test_user_deletion_api.py with tests for authenticated deletion, unauthenticated request (401), deletion removes all related records, sessions invalidated after deletion, and user can re-sign in after deletion

### Implementation for User Story 1

- [x] T005 [US1] Create UserDeletionService class in app/services/user_deletion_service.py with delete_user method that validates user exists, wraps hard_delete_user in transaction with rollback on error, logs deletion event with user_id/email/timestamp/method/status, sends Slack notification on success, and returns boolean success status
- [x] T006 [US1] Add DELETE /api/users/me endpoint in app/api/routes/users.py using get_current_user_id dependency, calling UserDeletionService.delete_user(), returning UserDeletionResponseDTO on success, handling exceptions with appropriate HTTP status codes (401/403/500)
- [x] T007 [US1] Add delete account button and confirmation dialog to app/templates/settings.html with prominent placement in settings page, clear warning about permanence, list of data to be deleted (profile/preferences/watchlist/notifications/email history), cancel and confirm buttons, JavaScript to show dialog on button click, call DELETE /api/users/me on confirm, handle success (redirect/logout), and handle errors with user-friendly messages

**Checkpoint**: At this point, User Story 1 should be fully functional and testable independently. Users can delete their accounts through the settings page.

---

## Phase 4: User Story 2 - Confirmation and Safety Measures (Priority: P2)

**Goal**: Enhance confirmation dialog with detailed information about what will be deleted and ensure proper authentication checks

**Independent Test**: Verify confirmation dialog appears with accurate deletion information, warning about permanence is clear, and unauthenticated deletion attempts are prevented

### Tests for User Story 2

- [x] T008 [P] [US2] Add test in tests/test_user_deletion_api.py for unauthenticated deletion request returns 401 and redirects to login
- [x] T009 [P] [US2] Add UI test scenario in tests/test_user_deletion_api.py verifying confirmation dialog displays complete list of data to be deleted

### Implementation for User Story 2

- [x] T010 [US2] Enhance confirmation dialog in app/templates/settings.html to clearly list all data types being deleted (user profile, preferences, watchlist tickers, notification settings, email send history, weekly digest history) with detailed explanation
- [x] T011 [US2] Add explicit warning text in confirmation dialog in app/templates/settings.html stating deletion cannot be undone and is permanent
- [x] T012 [US2] Verify authentication check in app/api/routes/users.py DELETE endpoint properly validates session and returns 401 if not authenticated (already handled by get_current_user_id dependency, but verify edge cases)

**Checkpoint**: At this point, User Stories 1 AND 2 should both work independently. Confirmation dialog provides comprehensive information and prevents accidental deletions.

---

## Phase 5: Polish & Cross-Cutting Concerns

**Purpose**: Final improvements, documentation, and validation

- [x] T013 [P] Run linting and formatting: `uv run ruff check --fix .`, `uv run black .`, `uv run mypy .` on all modified files
- [x] T014 [P] Update API documentation if needed to reflect new DELETE endpoint (API contract already exists in contracts/api.yaml)
- [x] T015 Verify all acceptance scenarios from spec.md are covered by tests
- [x] T016 [P] Test session invalidation by creating multiple sessions, deleting account, and verifying all sessions fail on next request
- [x] T017 [P] Test atomic transaction rollback by simulating database error during deletion and verifying no partial data deletion occurs
- [x] T018 [P] Test soft-deleted user deletion scenario to verify FR-012 (soft-deleted users can request permanent deletion)
- [x] T019 Verify Slack notification is sent successfully to market-pulse-users channel with correct information
- [x] T020 Run quickstart.md validation checklist to ensure all implementation steps are complete

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No setup tasks needed - existing infrastructure
- **Foundational (Phase 2)**: Must complete before user stories - provides DTO and Slack notification method
- **User Story 1 (Phase 3)**: Depends on Foundational completion - Core deletion functionality
- **User Story 2 (Phase 4)**: Depends on User Story 1 completion - Enhances confirmation dialog
- **Polish (Phase 5)**: Depends on all user stories being complete

### User Story Dependencies

- **User Story 1 (P1)**: Can start after Foundational (Phase 2) - No dependencies on other stories
- **User Story 2 (P2)**: Depends on User Story 1 - Enhances the confirmation dialog already created in US1

### Within Each User Story

- Tests MUST be written and FAIL before implementation
- Service layer before API endpoint
- API endpoint before UI
- Core implementation before integration
- Story complete before moving to next priority

### Parallel Opportunities

- **Foundational Phase**: T001 (DTO) and T002 (Slack method) can run in parallel
- **User Story 1 Tests**: T003 (unit tests) and T004 (integration tests) can run in parallel
- **User Story 1 Implementation**: T005 (service) can start after tests, then T006 (API) and T007 (UI) can be done sequentially
- **Polish Phase**: Most tasks marked [P] can run in parallel

---

## Parallel Example: User Story 1

```bash
# Launch all tests for User Story 1 together:
Task T003: "Create unit test file tests/test_user_deletion_service.py"
Task T004: "Create integration test file tests/test_user_deletion_api.py"

# After tests are written, launch foundational components in parallel:
Task T001: "Create UserDeletionResponseDTO in app/models/dto.py"
Task T002: "Add notify_user_deleted method to SlackService in app/services/slack_service.py"

# Then proceed sequentially:
Task T005: "Create UserDeletionService in app/services/user_deletion_service.py"
Task T006: "Add DELETE /api/users/me endpoint in app/api/routes/users.py"
Task T007: "Add delete account button and confirmation dialog to app/templates/settings.html"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 2: Foundational (T001, T002)
2. Complete Phase 3: User Story 1 (T003-T007)
   - Write tests first (T003, T004)
   - Implement service (T005)
   - Implement API endpoint (T006)
   - Implement UI (T007)
3. **STOP and VALIDATE**: Test User Story 1 independently
   - Navigate to settings page
   - Click delete account
   - Confirm deletion
   - Verify data removed from database
   - Sign in again and verify fresh account
4. Deploy/demo if ready

### Incremental Delivery

1. Complete Foundational → DTO and Slack notification ready
2. Add User Story 1 → Test independently → Deploy/Demo (MVP!)
   - Users can delete accounts
   - Confirmation dialog works
   - All data removed
   - Sessions invalidated
3. Add User Story 2 → Test independently → Deploy/Demo
   - Enhanced confirmation dialog
   - Better user education
   - Authentication edge cases handled
4. Polish → Final validation and cleanup

### Parallel Team Strategy

With multiple developers:

1. Team completes Foundational together (T001, T002 in parallel)
2. Once Foundational is done:
   - Developer A: Write tests (T003, T004 in parallel)
   - Developer B: Implement service (T005)
   - Developer C: Prepare UI mockup/structure
3. After tests and service:
   - Developer A: Implement API endpoint (T006)
   - Developer B: Implement UI (T007)
4. User Story 2 can be done by any developer after US1 is complete

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- Each user story should be independently completable and testable
- Verify tests fail before implementing
- Commit after each task or logical group
- Stop at any checkpoint to validate story independently
- Repository method `hard_delete_user()` already exists - no need to create it
- Session invalidation is automatic via existing `is_deleted` check in auth flow
- Database CASCADE constraints handle related record deletion automatically

