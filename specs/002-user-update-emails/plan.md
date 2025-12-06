# Implementation Plan: User Update Emails

**Branch**: `002-user-update-emails` | **Date**: 2025-01-27 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/002-user-update-emails/spec.md`

**Note**: This template is filled in by the `/speckit.plan` command. See `.specify/templates/commands/plan.md` for the execution workflow.

## Summary

Enable developers to send one-time update emails to all users via a Python script that reads email content and settings from a YAML/JSON config file. The script supports HTML email body, screenshot attachments via file paths, test mode for preview, and leverages existing email service infrastructure (AWS SES). This is a developer/admin tool, not a user-facing platform feature.

## Technical Context

**Language/Version**: Python 3.11+ (matches constitution)  
**Primary Dependencies**: 
- Existing: `app/services/email_service.py` (EmailService, SESEmailService)
- Existing: `app/repos/user_repo.py` (UserRepository)
- Existing: `app/config.py` (Settings for test_email_recipient)
- New: `pyyaml` or `json` (for config file parsing)
- New: `Pillow` (for image processing/validation, if needed)

**Storage**: 
- No new database tables required (uses existing User model)
- Config files: YAML/JSON files (developer-provided, not stored)
- Screenshot files: Local file system (read from paths, embedded in emails)

**Testing**: pytest (matches existing test infrastructure)  
**Target Platform**: Linux/macOS (developer workstation or server)  
**Project Type**: Single Python script (CLI tool)  
**Performance Goals**: 
- Send to 10,000 users without system degradation (SC-005)
- Script execution completes in reasonable time (rate-limited by email provider)

**Constraints**: 
- Must respect AWS SES rate limits (14 emails/second in sandbox, higher in production)
- Must handle large recipient lists gracefully (batch processing)
- Must validate config file before sending
- Must prevent accidental sends to all users (test mode default or explicit confirmation)

**Scale/Scope**: 
- Up to 10,000 recipients per email send
- Single developer/admin tool (not user-facing)
- Ad-hoc usage (one-time sends, not scheduled)

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

### I. Layered Architecture ✅ PASS
- **Script layer**: Standalone script that uses existing services/repos
- **No cross-layer violations**: Script calls `EmailService` and `UserRepository` (correct layer usage)
- **No new API layer**: This is a CLI script, not an API endpoint

### II. Type Safety & Code Quality ✅ PASS
- **Type hints**: All functions will have type hints
- **mypy --strict**: Must pass
- **ruff + black**: Must pass
- **Post-change checks**: Will run linting/formatting after implementation

### III. Configuration-Driven Design ✅ PASS
- **Config file**: YAML/JSON config file (external, not hardcoded)
- **Settings**: Uses existing `settings.test_email_recipient` from `app/config.py`
- **No magic numbers**: Email rate limits, batch sizes will be configurable

### IV. DTO Boundaries ✅ PASS
- **Uses existing DTOs**: `UserDTO` from `app/models/dto.py`
- **Email service**: Uses existing `EmailSendResult` DTO
- **No raw ORM objects**: Script will use repository methods that return DTOs

### V. UTC-First Temporal Data ✅ PASS
- **Timestamps**: Email send logs will use UTC timestamps
- **No timezone issues**: Script execution time is local, but logged data is UTC

### VI. Idempotent & Resumable Operations ⚠️ PARTIAL
- **Email sends**: Not idempotent by nature (emails are sent once)
- **Mitigation**: Test mode prevents accidental sends; explicit confirmation required for production sends
- **No resumption needed**: Script runs to completion or fails (no partial state)

### VII. Test-Driven Confidence ✅ PASS
- **Tests required**: Unit tests for script logic, integration tests for email sending
- **Test location**: `tests/scripts/test_send_update_email.py` or similar
- **Coverage**: Config parsing, user retrieval, email sending, error handling

**Overall Status**: ✅ **PASS** - All gates pass with one partial (acceptable for one-time email sends)

## Project Structure

### Documentation (this feature)

```text
specs/[###-feature]/
├── plan.md              # This file (/speckit.plan command output)
├── research.md          # Phase 0 output (/speckit.plan command)
├── data-model.md        # Phase 1 output (/speckit.plan command)
├── quickstart.md        # Phase 1 output (/speckit.plan command)
├── contracts/           # Phase 1 output (/speckit.plan command)
└── tasks.md             # Phase 2 output (/speckit.tasks command - NOT created by /speckit.plan)
```

### Source Code (repository root)

```text
app/
├── scripts/
│   └── send_update_email.py      # Main script (NEW)
├── services/
│   ├── email_service.py          # Existing (used by script)
│   └── update_email_service.py   # NEW: Service for update email logic
├── repos/
│   └── user_repo.py              # Existing (used by script)
└── models/
    └── dto.py                     # Existing (UserDTO used)

tests/
├── scripts/
│   └── test_send_update_email.py # NEW: Tests for script
└── unit/
    └── test_update_email_service.py  # NEW: Unit tests for service
```

**Structure Decision**: Single project structure. The script lives in `app/scripts/` alongside other scripts (e.g., `send_test_email.py`). A new service `UpdateEmailService` encapsulates the business logic for retrieving users, processing config, and sending emails. Tests follow existing patterns in `tests/` directory.

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

No violations - all constitution principles satisfied.

---

## Phase Completion Status

### Phase 0: Research ✅ COMPLETE

**Output**: `research.md`

**Resolved**:
- Config file format: YAML (better multi-line support)
- Screenshot embedding: Inline (CID) for better UX
- Rate limiting: Batch processing with configurable delay
- HTML email: Inline CSS, table-based layout
- Validation: Pydantic models

### Phase 1: Design & Contracts ✅ COMPLETE

**Outputs**:
- `data-model.md` - Config structure and data flow
- `contracts/config-schema.yaml` - Config file schema
- `quickstart.md` - Developer usage guide
- Agent context updated

**Design Decisions**:
- Config file: YAML with Pydantic validation
- Service layer: `UpdateEmailService` for business logic
- Script: `app/scripts/send_update_email.py` for CLI interface
- No new database tables (uses existing User model)

### Phase 2: Task Breakdown ⏳ PENDING

**Next Step**: Run `/speckit.tasks` to generate task breakdown

**Prerequisites Met**: ✅
- plan.md ✅
- spec.md ✅
- research.md ✅
- data-model.md ✅
- contracts/ ✅

---

## Ready for Implementation

All planning phases complete. Ready to proceed to task breakdown with `/speckit.tasks`.
