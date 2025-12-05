# Feature Specification: Delete User Account

**Feature Branch**: `001-delete-user`  
**Created**: 2025-01-27  
**Status**: Draft  
**Input**: User description: "I want to add \"delete user\" option. Currently the users are in the system once they signed."

## Clarifications

### Session 2025-01-27

- Q: Should all active sessions be immediately invalidated when an account is deleted, or is it acceptable for existing sessions to remain valid until they expire naturally? → A: Immediately invalidate all active sessions for the deleted user across all devices
- Q: If account deletion fails partway through (e.g., database error), should the system rollback all changes, retry the operation, or handle it differently? → A: Rollback all changes on failure (atomic transaction - all or nothing)
- Q: If a user who is already soft-deleted requests permanent account deletion, should the system proceed with hard delete, or should it prevent/ignore the request? → A: Proceed with hard delete (allow soft-deleted users to permanently delete)
- Q: What information should be logged when an account is deleted? → A: Log user ID, email, timestamp, deletion method (user-initiated vs admin), and success/failure status
- Q: Should the system send notifications when an account is deleted? → A: Send Slack notification to market-pulse-users channel when account deletion completes successfully

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Delete Account from Settings (Priority: P1)

A user wants to permanently delete their account and all associated data from the system. They navigate to the settings page and find a "Delete Account" option. When they click it, they are shown a confirmation dialog explaining what will be deleted. After confirming, their account and all related data are permanently removed from the database. The next time they sign in with the same authentication provider, they will be treated as a new user with default preferences and no watchlist tickers.

**Why this priority**: This is the core functionality - without this, users cannot delete their accounts at all. It provides users with control over their data and meets privacy/data protection requirements.

**Independent Test**: Can be fully tested by navigating to settings, clicking delete account, confirming deletion, and verifying that all user data is removed from the database. The user can then sign in again and verify they start with a fresh account.

**Acceptance Scenarios**:

1. **Given** a user is logged in and viewing the settings page, **When** they click the "Delete Account" button, **Then** a confirmation dialog appears explaining what data will be deleted
2. **Given** the confirmation dialog is displayed, **When** the user clicks "Cancel", **Then** the dialog closes and no data is deleted
3. **Given** the confirmation dialog is displayed, **When** the user clicks "Confirm Delete", **Then** their account and all related data are permanently deleted from all tables
4. **Given** a user has deleted their account, **When** they sign in again with the same authentication provider, **Then** a new account is created with default preferences and no watchlist tickers
5. **Given** a user has deleted their account, **When** they attempt to access any authenticated endpoint, **Then** they are redirected to login and treated as a new user
6. **Given** a user has active sessions on multiple devices, **When** their account is deleted, **Then** all active sessions across all devices are immediately invalidated
7. **Given** a user confirms account deletion, **When** the deletion operation fails partway through (e.g., database error), **Then** all changes are rolled back atomically and the user receives an error message indicating the deletion failed
8. **Given** a user who is already soft-deleted requests permanent account deletion, **When** they confirm the deletion, **Then** the system proceeds with hard delete and permanently removes all data
9. **Given** a user successfully deletes their account, **When** the deletion completes, **Then** a Slack notification is sent to the market-pulse-users channel with account deletion details

---

### User Story 2 - Confirmation and Safety Measures (Priority: P2)

To prevent accidental deletions, the system requires explicit confirmation before deleting an account. The confirmation dialog clearly explains what will be deleted and warns that the action cannot be undone. The delete action may require re-authentication or additional verification to ensure the user is authorized to perform this action.

**Why this priority**: Prevents accidental data loss and provides transparency about what will be deleted. This is important for user trust and data protection compliance.

**Independent Test**: Can be tested independently by verifying that the confirmation dialog appears, displays accurate information about what will be deleted, and that cancellation works correctly.

**Acceptance Scenarios**:

1. **Given** a user clicks "Delete Account", **When** the confirmation dialog appears, **Then** it clearly lists what data will be deleted (profile, preferences, watchlist tickers, notification settings, email history)
2. **Given** the confirmation dialog is displayed, **When** the user reads the warning that deletion cannot be undone, **Then** they understand the permanence of the action
3. **Given** a user attempts to delete their account, **When** they are not properly authenticated, **Then** the deletion is prevented and they are redirected to login

---

### Edge Cases

- What happens when a user tries to delete their account while they have pending email notifications?
- What happens if a user tries to delete their account immediately after creating it?

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST provide a "Delete Account" option in the user settings page
- **FR-002**: System MUST display a confirmation dialog before deleting an account that explains what data will be deleted
- **FR-003**: System MUST require explicit user confirmation before proceeding with account deletion
- **FR-004**: System MUST permanently delete the user record from the users table when deletion is confirmed
- **FR-005**: System MUST permanently delete all related user data from all tables (user_profiles, user_notification_channels, user_ticker_follows, email_send_log, weekly_digest_send_record) when a user account is deleted
- **FR-006**: System MUST ensure that deleted users cannot access authenticated endpoints by immediately invalidating all active sessions across all devices when account deletion is confirmed
- **FR-007**: System MUST allow users who have deleted their account to sign in again and create a new account with the same authentication provider
- **FR-008**: System MUST initialize new accounts created after deletion with default preferences (no custom preferences, no watchlist tickers)
- **FR-009**: System MUST handle deletion requests only from authenticated users who own the account being deleted
- **FR-010**: System MUST log account deletion events for audit purposes, including user ID, email, timestamp, deletion method (user-initiated vs admin), and success/failure status
- **FR-011**: System MUST perform account deletion as an atomic transaction, rolling back all changes if any part of the deletion fails
- **FR-012**: System MUST allow soft-deleted users to request permanent account deletion and proceed with hard delete
- **FR-013**: System MUST send a Slack notification to the market-pulse-users channel when account deletion completes successfully

### Key Entities *(include if feature involves data)*

- **User Account**: Represents the authenticated user with email, authentication provider information, and account status
- **User Profile**: Contains user preferences, display name, timezone, and other profile information (deleted when user is deleted)
- **User Notification Channels**: Email and other notification preferences (deleted when user is deleted)
- **User Ticker Follows**: Watchlist tickers and notification preferences for specific tickers (deleted when user is deleted)
- **Email Send Log**: Historical record of emails sent to the user (deleted when user is deleted)
- **Weekly Digest Send Record**: Historical record of weekly digest emails sent (deleted when user is deleted)

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Users can delete their account from the settings page in under 30 seconds from clicking the delete button to receiving confirmation
- **SC-002**: 100% of user-related data is removed from all database tables when account deletion is confirmed
- **SC-003**: Users who delete their account and sign in again successfully create a new account with default preferences within 5 seconds of authentication
- **SC-004**: Zero accidental deletions occur due to unclear UI or missing confirmation (measured by support tickets or user reports)
- **SC-005**: Account deletion completes successfully for 99.9% of deletion requests (allowing for edge cases like concurrent operations)

## Assumptions

- Users understand that account deletion is permanent and cannot be undone
- The database foreign key constraints with CASCADE delete are properly configured to automatically delete related records
- Users will sign in again using the same authentication provider (e.g., same Google account) after deletion
- No business-critical data needs to be retained after user deletion (e.g., anonymized analytics may be acceptable)
- The confirmation dialog provides sufficient information for users to make an informed decision
- Account deletion does not require additional verification beyond the confirmation dialog (e.g., password re-entry)

## Dependencies

- User authentication and session management must be functional
- Settings page must exist and be accessible to authenticated users
- Database foreign key constraints with CASCADE delete must be properly configured
- User repository must support hard delete operations (already exists as `hard_delete_user` method)
- Slack integration must be configured and accessible for sending notifications to market-pulse-users channel

## Out of Scope

- Soft delete functionality (already exists, but this feature requires hard delete)
- Account recovery or restoration after deletion
- Partial data deletion (e.g., deleting only watchlist while keeping profile)
- Exporting user data before deletion
- Anonymizing user data instead of deleting it
- Multi-factor authentication for deletion confirmation
- Grace period or delayed deletion
