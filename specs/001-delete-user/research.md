# Research: Delete User Account Feature

**Date**: 2025-01-27  
**Feature**: Delete User Account  
**Branch**: `001-delete-user`

## Research Questions

### 1. Session Invalidation Strategy for JWT Tokens

**Question**: How should we invalidate all active sessions when a user deletes their account, given that JWT tokens are stateless?

**Decision**: Use database-backed session tracking with immediate invalidation.

**Rationale**: 
- Current system uses stateless JWT tokens stored in HTTP-only cookies
- Stateless JWTs cannot be revoked without additional infrastructure
- Options considered:
  1. **Token blacklist in Redis**: Requires Redis, adds complexity, but provides immediate invalidation
  2. **Database session table**: Track active sessions, delete on account deletion, check on each request
  3. **Short token expiration + refresh tokens**: Doesn't solve immediate invalidation requirement
  4. **Database check on each request**: Query user existence on each authenticated request (already done)

**Chosen Approach**: 
- Leverage existing `get_current_user` flow which already queries database and checks `is_deleted` flag
- Since user record is deleted, all subsequent token verifications will fail (user not found)
- This provides immediate invalidation without additional infrastructure
- Note: Tokens remain valid until expiration, but user lookup will fail, effectively invalidating them

**Alternatives Considered**:
- Redis blacklist: Rejected due to added infrastructure complexity and Redis dependency for core auth flow
- Session table: Rejected as it requires schema changes and additional queries on every request

**References**:
- Existing code: `app/services/auth_service.py::get_current_user` already filters by `is_deleted == False`
- JWT best practices: Stateless tokens with database validation for revocation

### 2. Atomic Transaction Pattern for User Deletion

**Question**: How to ensure atomic deletion across multiple tables with proper error handling?

**Decision**: Use SQLAlchemy session transaction with explicit rollback on exception.

**Rationale**:
- Database CASCADE constraints handle related record deletion automatically
- SQLAlchemy sessions provide transaction boundaries
- Need explicit error handling to ensure rollback on any failure
- Must wrap entire operation in try/except with rollback

**Chosen Approach**:
```python
try:
    # Hard delete user (CASCADE handles related records)
    repo.hard_delete_user(user_id)
    # Invalidate sessions (no-op if user already deleted)
    # Send Slack notification
    # Log deletion
    db.commit()
except Exception:
    db.rollback()
    raise
```

**Alternatives Considered**:
- Manual deletion of each table: Rejected - CASCADE constraints already handle this
- Two-phase commit: Rejected - Overkill for single database operation
- Event-driven deletion: Rejected - Adds complexity, violates atomicity requirement

**References**:
- SQLAlchemy documentation: Session transactions
- Existing code: `app/repos/user_repo.py::hard_delete_user` method

### 3. Slack Notification Format for User Deletion

**Question**: What information should be included in Slack notification for account deletion?

**Decision**: Include user ID, email, timestamp, and deletion method (user-initiated).

**Rationale**:
- Matches audit logging requirements (FR-010)
- Provides sufficient context for team awareness
- Consistent with existing `notify_user_created` pattern
- Privacy-conscious (no sensitive data beyond email)

**Chosen Approach**:
- Use existing `SlackService.send_message` method
- Create new `notify_user_deleted` method following `notify_user_created` pattern
- Send to `market-pulse-users` channel (already configured)
- Include: user_id, email, deleted_at timestamp, environment

**Alternatives Considered**:
- Minimal notification (user ID only): Rejected - insufficient context
- Comprehensive notification (all user data): Rejected - privacy concerns, too verbose

**References**:
- Existing code: `app/services/slack_service.py::notify_user_created`
- Spec requirement: FR-013

### 4. Error Handling and User Feedback

**Question**: How should deletion failures be communicated to users?

**Decision**: Return HTTP 500 with generic error message, log detailed error for debugging.

**Rationale**:
- User-facing errors should be generic (security best practice)
- Detailed errors logged for debugging
- Atomic transaction ensures no partial state
- User can retry if transient error

**Chosen Approach**:
- Catch all exceptions in service layer
- Log full error details with context
- Return HTTP 500 with message: "Account deletion failed. Please try again or contact support."
- Slack notification includes error details (if configured)

**Alternatives Considered**:
- Specific error messages per failure type: Rejected - exposes system internals
- Silent failure: Rejected - user needs feedback

**References**:
- Security best practices: Don't expose internal errors to users
- Existing patterns: Other API endpoints use generic error messages

## Technical Decisions Summary

| Decision Area | Chosen Approach | Rationale |
|--------------|----------------|-----------|
| Session Invalidation | Database check on each request (existing flow) | Leverages existing `is_deleted` check, no new infrastructure |
| Atomic Deletion | SQLAlchemy transaction with rollback | Standard pattern, CASCADE handles related records |
| Slack Notification | New method following existing pattern | Consistency, sufficient context |
| Error Handling | Generic user message, detailed logging | Security and debugging balance |

## Dependencies Identified

- **Existing**: `UserRepository.hard_delete_user()` method
- **Existing**: `SlackService` with channel configuration
- **Existing**: Database CASCADE constraints on foreign keys
- **Existing**: `AuthService.get_current_user()` with `is_deleted` check
- **New**: `UserDeletionService` to orchestrate deletion flow
- **New**: API endpoint `DELETE /api/users/me`
- **New**: UI confirmation dialog in settings page

## Open Questions Resolved

✅ All technical questions resolved. No blocking unknowns remain.

## Next Steps

Proceed to Phase 1: Design & Contracts
- Create data model documentation
- Define API contract (OpenAPI)
- Create quickstart guide

