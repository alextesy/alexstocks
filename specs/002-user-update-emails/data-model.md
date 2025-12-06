# Data Model: User Update Emails

**Feature**: 002-user-update-emails  
**Date**: 2025-01-27

## Overview

This feature does not introduce new database tables. It uses existing entities and introduces a config file structure for the Python script.

## Config File Structure (Pydantic Model)

### UpdateEmailConfig

Represents the configuration file structure for update emails.

**Location**: `app/models/dto.py` (new model)

**Fields**:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `subject` | `str` | Yes | Email subject line (1-200 characters) |
| `body_html` | `str` | Yes | HTML email body content (non-empty) |
| `screenshots` | `list[str]` | No | List of file paths to screenshot images (relative or absolute) |
| `test_mode` | `bool` | Yes | If true, send only to test user; if false, send to all users |
| `batch_size` | `int` | No | Number of emails per batch (default: 14, min: 1, max: 100) |
| `batch_delay_seconds` | `float` | No | Delay between batches in seconds (default: 1.0, min: 0.0) |

**Validation Rules**:
- `subject`: Must be non-empty, trimmed, max 200 characters
- `body_html`: Must be non-empty, trimmed
- `screenshots`: Each path must exist and be readable; files must be images (PNG, JPG, GIF); max 10 screenshots
- `test_mode`: Required boolean
- `batch_size`: Must be between 1 and 100 (default: 14)
- `batch_delay_seconds`: Must be >= 0.0 (default: 1.0)

**Example**:

```yaml
subject: "New Features Available!"
body_html: |
  <h1>Check out our latest updates!</h1>
  <p>We've added some exciting new features...</p>
screenshots:
  - "screenshots/feature1.png"
  - "screenshots/feature2.jpg"
test_mode: true
batch_size: 14
batch_delay_seconds: 1.0
```

## Existing Entities Used

### User (from `app/db/models.py`)

**Used Fields**:
- `id`: User ID
- `email`: Email address
- `is_active`: Active status (must be True)
- `is_deleted`: Soft delete flag (must be False)

**Filtering**:
- Only active, non-deleted users
- Only users with verified email addresses (via `UserNotificationChannel`)

### UserNotificationChannel (from `app/db/models.py`)

**Used Fields**:
- `user_id`: Foreign key to User
- `channel_type`: Must be "email"
- `is_enabled`: Must be True
- `is_verified`: Must be True
- `email_bounced`: Must be False

**Purpose**: Filter users eligible to receive emails

## Data Flow

```
Config File (YAML)
    ↓
UpdateEmailConfig (Pydantic validation)
    ↓
UpdateEmailService
    ↓
UserRepository.get_eligible_users()
    ↓
List[UserDTO]
    ↓
EmailService.send_email() (per user, batched)
    ↓
EmailSendResult (per user)
    ↓
Summary Report (success/failure counts)
```

## State Transitions

### Email Send Process

```
[Config File Loaded]
    ↓
[Config Validated]
    ↓
[Users Retrieved]
    ↓
[Batch Processing Started]
    ↓
For each batch:
    [Send emails in batch]
    [Wait batch_delay_seconds]
    ↓
[All batches complete]
    ↓
[Summary Report Generated]
```

### Error States

- **Config Invalid**: Script exits with error, no emails sent
- **No Eligible Users**: Script reports warning, exits successfully
- **Partial Failures**: Script continues, reports failures in summary
- **Rate Limit Hit**: Script waits/retries (handled by email service)

## No Persistent Storage

This feature does not persist email send history to the database. Logging is handled via:
- Structured logging (Python `logging` module)
- Console output (summary report)
- Email service logs (existing infrastructure)

If future requirements need email send history, a new table could be added:
- `update_email_sends`: id, subject, sent_at, recipient_count, success_count, failure_count, sender_email

But this is **out of scope** for the current feature.

