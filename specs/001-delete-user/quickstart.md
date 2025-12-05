# Quickstart: Delete User Account Feature

**Feature**: Delete User Account  
**Date**: 2025-01-27  
**Branch**: `001-delete-user`

## Overview

This guide provides a quick reference for implementing the delete user account feature. It covers the key components, API endpoint, and UI changes needed.

## Architecture Summary

```
User clicks "Delete Account" in Settings
    ↓
Frontend: Confirmation dialog
    ↓
Frontend: DELETE /api/users/me
    ↓
API: Validates authentication
    ↓
Service: UserDeletionService.delete_user()
    ├── Repository: hard_delete_user() [atomic transaction]
    ├── Session: Invalidated automatically (user lookup fails)
    ├── Logging: Audit log entry
    └── Slack: Notification sent
    ↓
Response: Success/Error
```

## Implementation Checklist

### 1. Service Layer (`app/services/user_deletion_service.py`)

**New File**: Create service to orchestrate deletion flow

```python
class UserDeletionService:
    def delete_user(self, user_id: int, db: Session) -> bool:
        """
        1. Validate user exists
        2. Start transaction
        3. Call repo.hard_delete_user()
        4. Log deletion event
        5. Send Slack notification
        6. Commit (or rollback on error)
        """
```

**Key Points**:
- Wrap entire operation in try/except with rollback
- Log before deletion (user_id, email available)
- Send Slack notification after successful deletion
- Return boolean success status

### 2. API Endpoint (`app/api/routes/users.py`)

**Add to existing router**:

```python
@router.delete("/me", response_model=UserDeletionResponseDTO)
async def delete_current_user(
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """
    DELETE /api/users/me
    - Requires authentication (session_token cookie)
    - Deletes current user's account
    - Returns success response
    """
```

**Key Points**:
- Use existing `get_current_user_id` dependency
- Call `UserDeletionService.delete_user()`
- Return DTO response
- Handle exceptions with appropriate HTTP status codes

### 3. DTO (`app/models/dto.py`)

**Add new DTO**:

```python
class UserDeletionResponseDTO(BaseModel):
    success: bool
    message: str
```

**Key Points**:
- Simple response model
- Success flag and message
- Used for API response

### 4. Slack Service (`app/services/slack_service.py`)

**Add new method**:

```python
def notify_user_deleted(
    self,
    user_id: int,
    email: str,
    environment: str | None = None,
) -> None:
    """
    Send notification to market-pulse-users channel
    Include: user_id, email, timestamp, environment
    """
```

**Key Points**:
- Follow existing `notify_user_created` pattern
- Use `self._users_channel` (already configured)
- Include user_id, email, timestamp, environment
- Use Slack blocks for rich formatting

### 5. UI Changes (`app/templates/settings.html`)

**Add delete account section**:

```html
<!-- Delete Account Section -->
<div class="mt-8 border-t pt-8">
  <h2 class="text-xl font-bold text-red-600 mb-4">Delete Account</h2>
  <p class="text-gray-600 mb-4">
    Permanently delete your account and all associated data. This action cannot be undone.
  </p>
  <button id="delete-account-btn" class="bg-red-600 text-white px-4 py-2 rounded">
    Delete Account
  </button>
</div>

<!-- Confirmation Modal -->
<div id="delete-confirm-modal" class="hidden">
  <!-- Modal content with:
       - Warning message
       - List of data to be deleted
       - Cancel and Confirm buttons
  -->
</div>
```

**JavaScript**:
- Show confirmation dialog on button click
- List what will be deleted (profile, preferences, watchlist, etc.)
- On confirm, call `DELETE /api/users/me`
- Handle success (redirect to home/logout)
- Handle errors (show error message)

**Key Points**:
- Prominent but not intrusive placement
- Clear warning about permanence
- List of data to be deleted
- Two-step confirmation (button → dialog → API call)

### 6. Repository (`app/repos/user_repo.py`)

**Existing Method**: `hard_delete_user()` already exists

**No Changes Required**: Method already implements hard delete with CASCADE handling

**Key Points**:
- Method exists at line 169-177
- Uses `session.delete(user)` which triggers CASCADE
- Returns boolean success status

### 7. Session Invalidation

**Automatic**: No code changes needed

**How it works**:
- `AuthService.get_current_user()` already checks `is_deleted == False`
- After deletion, user record doesn't exist
- Token verification succeeds, but user lookup fails
- Effectively invalidates all sessions immediately

**Key Points**:
- Leverages existing authentication flow
- No additional infrastructure needed
- Immediate invalidation on next request

## Testing Strategy

### Unit Tests (`tests/test_user_deletion_service.py`)

**Test Cases**:
1. Successful deletion
2. User not found
3. Database error (rollback)
4. Slack notification failure (non-blocking)
5. Audit logging

### Integration Tests (`tests/test_user_deletion_api.py`)

**Test Cases**:
1. Authenticated user can delete account
2. Unauthenticated request returns 401
3. Deletion removes all related records
4. Sessions invalidated after deletion
5. User can re-sign in after deletion

### UI Tests (Manual)

**Test Cases**:
1. Confirmation dialog appears
2. Cancel closes dialog without deletion
3. Confirm triggers deletion
4. Success redirects appropriately
5. Error shows user-friendly message

## Configuration

### Environment Variables

**Existing** (no new variables needed):
- `SLACK_BOT_TOKEN`: Slack bot token
- `SLACK_USERS_CHANNEL`: Channel ID for user notifications

### Settings (`app/config.py`)

**No new settings required**: All configuration already exists

## Deployment Considerations

### Database

**No migrations required**: CASCADE constraints already in place

### Backward Compatibility

**Fully compatible**: New endpoint, no breaking changes

### Rollback Plan

**Simple**: Remove endpoint and UI changes, service can remain (unused)

## Success Criteria Validation

- ✅ **SC-001**: Deletion completes in <30 seconds (atomic transaction)
- ✅ **SC-002**: 100% data removal (CASCADE constraints ensure this)
- ✅ **SC-003**: Re-authentication works (existing auth flow)
- ✅ **SC-004**: Zero accidental deletions (confirmation dialog)
- ✅ **SC-005**: 99.9% success rate (atomic transaction with rollback)

## Next Steps

1. Implement `UserDeletionService`
2. Add API endpoint
3. Add DTO
4. Add Slack notification method
5. Update UI with delete button and confirmation
6. Write tests
7. Deploy

## References

- **Spec**: [spec.md](./spec.md)
- **Plan**: [plan.md](./plan.md)
- **Data Model**: [data-model.md](./data-model.md)
- **API Contract**: [contracts/api.yaml](./contracts/api.yaml)
- **Research**: [research.md](./research.md)

