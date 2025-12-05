# Data Model: Delete User Account

**Feature**: Delete User Account  
**Date**: 2025-01-27  
**Branch**: `001-delete-user`

## Overview

This feature does not introduce new database tables or modify existing schemas. It leverages existing user-related tables with CASCADE delete constraints to ensure complete data removal.

## Affected Entities

### User (Primary Entity)

**Table**: `users`  
**Action**: Hard delete (permanent removal)

**Fields**:
- `id` (BigInteger, PK): User identifier
- `email` (String, UNIQUE): User email address
- `auth_provider_id` (String, UNIQUE): OAuth provider ID (e.g., Google sub)
- `auth_provider` (String): Provider name (e.g., 'google')
- `is_active` (Boolean): Account active status
- `is_deleted` (Boolean): Soft delete flag (not used in hard delete)
- `created_at` (DateTime, TZ): Account creation timestamp
- `updated_at` (DateTime, TZ): Last update timestamp
- `deleted_at` (DateTime, TZ, nullable): Soft delete timestamp (not used in hard delete)

**Deletion Behavior**: 
- Hard delete removes record permanently
- CASCADE constraints automatically delete related records in dependent tables

### UserProfile (Cascade Delete)

**Table**: `user_profiles`  
**Action**: Automatic deletion via CASCADE constraint

**Foreign Key**: `user_id` → `users.id` with `ON DELETE CASCADE`

**Fields Deleted**:
- `user_id` (BigInteger, PK, FK): References users.id
- `display_name` (String): User display name
- `timezone` (String): User timezone preference
- `avatar_url` (String): Avatar image URL
- `bio` (Text): User biography
- `preferences` (JSONB): User preferences (including notification defaults, email cadence)

**Deletion Behavior**: Automatically deleted when parent `users` record is deleted

### UserNotificationChannel (Cascade Delete)

**Table**: `user_notification_channels`  
**Action**: Automatic deletion via CASCADE constraint

**Foreign Key**: `user_id` → `users.id` with `ON DELETE CASCADE`

**Fields Deleted**:
- `id` (BigInteger, PK)
- `user_id` (BigInteger, FK): References users.id
- `channel_type` (String): Channel type ('email', 'sms', etc.)
- `channel_value` (String): Channel address/value
- `is_verified` (Boolean): Verification status
- `is_enabled` (Boolean): Enable status
- `preferences` (JSONB): Channel-specific preferences
- `email_bounced` (Boolean): Email bounce status
- `bounced_at` (DateTime, TZ): Bounce timestamp
- `bounce_type` (String): Bounce type

**Deletion Behavior**: Automatically deleted when parent `users` record is deleted

### UserTickerFollow (Cascade Delete)

**Table**: `user_ticker_follows`  
**Action**: Automatic deletion via CASCADE constraint

**Foreign Key**: `user_id` → `users.id` with `ON DELETE CASCADE`

**Fields Deleted**:
- `id` (BigInteger, PK)
- `user_id` (BigInteger, FK): References users.id
- `ticker` (String, FK): Ticker symbol
- `notify_on_signals` (Boolean): Signal notification preference
- `notify_on_price_change` (Boolean): Price change notification preference
- `price_change_threshold` (Float): Price change threshold
- `custom_alerts` (JSONB): Custom alert conditions
- `order` (Integer): Display order in watchlist

**Deletion Behavior**: Automatically deleted when parent `users` record is deleted

### EmailSendLog (Cascade Delete)

**Table**: `email_send_log`  
**Action**: Automatic deletion via CASCADE constraint

**Foreign Key**: `user_id` → `users.id` with `ON DELETE CASCADE`

**Fields Deleted**:
- `id` (BigInteger, PK)
- `user_id` (BigInteger, FK): References users.id
- `email_address` (String): Email address used
- `summary_date` (Date): Summary date
- `ticker_count` (Integer): Number of tickers in email
- `success` (Boolean): Send success status
- `message_id` (String): Email provider message ID
- `error` (Text): Error message if failed
- `provider` (String): Email provider name
- `sent_at` (DateTime, TZ): Send timestamp

**Deletion Behavior**: Automatically deleted when parent `users` record is deleted

### WeeklyDigestSendRecord (Cascade Delete)

**Table**: `weekly_digest_send_record`  
**Action**: Automatic deletion via CASCADE constraint

**Foreign Key**: `user_id` → `users.id` with `ON DELETE CASCADE`

**Fields Deleted**:
- `id` (BigInteger, PK)
- `user_id` (BigInteger, FK): References users.id
- `week_start_date` (Date): Week start date
- `status` (String): Send status ('pending', 'sent', 'failed', 'skipped')
- `ticker_count` (Integer): Number of tickers in digest
- `days_with_data` (Integer): Days with data in week
- `message_id` (String): Email provider message ID
- `error` (Text): Error message if failed
- `skip_reason` (String): Reason for skipping
- `created_at` (DateTime, TZ): Record creation timestamp
- `sent_at` (DateTime, TZ): Send timestamp

**Deletion Behavior**: Automatically deleted when parent `users` record is deleted

## Data Flow

```
User initiates deletion
    ↓
API endpoint validates authentication
    ↓
Service layer starts transaction
    ↓
Repository.hard_delete_user(user_id)
    ↓
Database CASCADE constraints:
    ├── user_profiles deleted
    ├── user_notification_channels deleted
    ├── user_ticker_follows deleted
    ├── email_send_log deleted
    └── weekly_digest_send_record deleted
    ↓
Transaction commit (or rollback on error)
    ↓
Session invalidation (automatic via is_deleted check)
    ↓
Audit logging
    ↓
Slack notification
```

## Validation Rules

### Pre-Deletion Validation

1. **Authentication**: User must be authenticated (session token valid)
2. **Ownership**: User can only delete their own account (user_id matches session)
3. **Existence**: User must exist (not already deleted)

### Post-Deletion State

1. **User Record**: Permanently removed from `users` table
2. **Related Records**: All related records removed via CASCADE
3. **Sessions**: All active sessions invalidated (user lookup fails)
4. **Re-authentication**: User can sign in again, new account created

## State Transitions

```
[Active User] 
    ↓ (DELETE /api/users/me)
[Deletion Request]
    ↓ (Transaction starts)
[Deletion In Progress]
    ↓ (CASCADE deletes related records)
[User Deleted]
    ↓ (Transaction commits)
[Account Removed]
    ↓ (User signs in again)
[New Account Created]
```

## Constraints

### Database Constraints

- **CASCADE DELETE**: All foreign keys to `users.id` have `ON DELETE CASCADE`
- **UNIQUE Constraints**: Email and auth_provider_id uniqueness allows re-use after deletion
- **NOT NULL**: Required fields enforced at database level

### Business Constraints

- **Atomic Operation**: All deletions must succeed or all rollback
- **Immediate Effect**: Deletion takes effect immediately (no grace period)
- **No Recovery**: Deleted accounts cannot be restored
- **Re-authentication**: Same email/auth_provider_id can create new account

## Indexes

No new indexes required. Existing indexes support the deletion operation:
- `user_email_idx`: Fast lookup by email (for re-authentication)
- `user_auth_provider_id_idx`: Fast lookup by provider ID (for re-authentication)
- `user_is_deleted_idx`: Filters soft-deleted users (not used in hard delete)

## Data Retention

**Policy**: Complete removal of all user data upon account deletion.

**Retention Period**: 0 days (immediate deletion)

**Exceptions**: None. All user-related data is permanently deleted.

**Audit Trail**: Deletion events logged for audit purposes (FR-010), but user data itself is removed.

## Migration Requirements

**Schema Changes**: None required. Existing CASCADE constraints handle related record deletion.

**Data Migration**: None required.

**Backward Compatibility**: Existing soft-delete functionality remains unchanged. Hard delete is a new operation.

