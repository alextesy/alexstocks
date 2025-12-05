# Implementation Plan: Delete User Account

**Branch**: `001-delete-user` | **Date**: 2025-01-27 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/001-delete-user/spec.md`

## Summary

Implement a user-initiated account deletion feature that permanently removes user data from all database tables. The feature includes a confirmation dialog in the settings page, atomic transaction-based deletion with rollback on failure, immediate session invalidation across all devices, comprehensive audit logging, and Slack notifications. Users can re-sign in after deletion and will be treated as new users with default preferences.

**Technical Approach**: Leverage existing `hard_delete_user` repository method with database CASCADE constraints. Add session invalidation via JWT token blacklisting or database-backed session tracking. Use existing SlackService for notifications. Implement atomic transaction wrapper to ensure all-or-nothing deletion.

## Technical Context

**Language/Version**: Python 3.11+ (compatible with 3.12)  
**Primary Dependencies**: FastAPI, SQLAlchemy 2.x, Pydantic, slack-sdk, PyJWT  
**Storage**: PostgreSQL 16 (with CASCADE foreign key constraints)  
**Testing**: pytest with integration tests using Docker Compose PostgreSQL  
**Target Platform**: Linux server (EC2 for API, ECS Fargate for jobs)  
**Project Type**: Web application (FastAPI backend with Jinja2 templates)  
**Performance Goals**: Account deletion completes in <30 seconds (SC-001), 99.9% success rate (SC-005)  
**Constraints**: Atomic transaction required (FR-011), must invalidate all sessions immediately (FR-006), must log deletion events (FR-010)  
**Scale/Scope**: Single API endpoint, one settings page UI component, affects all user-related tables (6 tables total)

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

### I. Layered Architecture ✅

- **API Layer** (`app/api/routes/users.py`): New DELETE endpoint will use DTOs, no direct DB access
- **Service Layer** (`app/services/`): New `user_deletion_service.py` will orchestrate deletion, session invalidation, logging, and Slack notification
- **Repository Layer** (`app/repos/user_repo.py`): Existing `hard_delete_user` method already exists; may need session invalidation helper
- **Database Layer**: CASCADE constraints handle related record deletion automatically

**Compliance**: ✅ All layers respected. No cross-layer imports.

### II. Type Safety & Code Quality ✅

- All new functions will have type hints
- `mypy --strict` must pass
- `ruff check` and `black` formatting required
- DTOs for request/response validation

**Compliance**: ✅ Standard development workflow applies.

### III. Configuration-Driven Design ✅

- Session invalidation strategy configurable (if needed)
- Slack channel already configured via `settings.slack_users_channel`
- Audit log format configurable

**Compliance**: ✅ No magic numbers or hardcoded values.

### IV. DTO Boundaries ✅

- Request DTO: `UserDeletionRequestDTO` (if needed, or use empty body)
- Response DTO: `UserDeletionResponseDTO` with success status
- No raw ORM objects exposed to API

**Compliance**: ✅ DTOs required at API boundaries.

### V. UTC-First Temporal Data ✅

- Deletion timestamp stored in UTC
- Audit logs use UTC timestamps
- Slack notifications include UTC timestamps

**Compliance**: ✅ All timestamps in UTC.

### VI. Idempotent & Resumable Operations ✅

- Deletion is idempotent: deleting already-deleted user returns success (no-op)
- Atomic transaction ensures no partial state

**Compliance**: ✅ Idempotent operation.

### VII. Test-Driven Confidence ✅

- Unit tests for service layer
- Integration tests for full deletion flow
- Contract tests for API endpoint

**Compliance**: ✅ Tests required before merge.

**Gate Status**: ✅ **PASS** - All principles satisfied. No violations detected.

## Project Structure

### Documentation (this feature)

```text
specs/001-delete-user/
├── plan.md              # This file (/speckit.plan command output)
├── research.md          # Phase 0 output (/speckit.plan command)
├── data-model.md        # Phase 1 output (/speckit.plan command)
├── quickstart.md        # Phase 1 output (/speckit.plan command)
├── contracts/           # Phase 1 output (/speckit.plan command)
│   └── api.yaml        # OpenAPI spec for DELETE /api/users/me endpoint
└── tasks.md             # Phase 2 output (/speckit.tasks command - NOT created by /speckit.plan)
```

### Source Code (repository root)

```text
app/
├── api/
│   └── routes/
│       └── users.py              # Add DELETE /api/users/me endpoint
├── services/
│   ├── user_deletion_service.py  # NEW: Orchestrates deletion flow
│   └── slack_service.py          # EXISTING: Add notify_user_deleted method
├── repos/
│   └── user_repo.py              # EXISTING: hard_delete_user method already exists
├── models/
│   └── dto.py                    # Add UserDeletionResponseDTO
└── templates/
    └── settings.html             # Add delete account button and confirmation dialog

tests/
├── test_user_deletion_service.py # NEW: Unit tests for deletion service
├── test_user_deletion_api.py     # NEW: Integration tests for API endpoint
└── test_auth_integration.py      # EXISTING: May need updates for session invalidation
```

**Structure Decision**: Web application structure. New service layer component (`user_deletion_service.py`) follows existing patterns. API endpoint added to existing `users.py` router. UI changes in existing `settings.html` template. All changes fit within existing architecture.

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

No violations detected. All changes comply with constitution principles.
