# Quickstart: Sending Update Emails

**Feature**: 002-user-update-emails  
**Date**: 2025-01-27

## Overview

The `send_update_email.py` script allows developers to send one-time update emails to all users or to a test user for preview. The script reads email content and settings from a YAML config file.

## Prerequisites

1. **Database Access**: Script must be able to connect to PostgreSQL database
2. **Email Service**: AWS SES must be configured and operational
3. **Test Email**: `TEST_EMAIL_RECIPIENT` must be configured in `.env` or environment
4. **Dependencies**: `pyyaml` installed (if using YAML config)

## Quick Start

### 1. Create Config File

Create a YAML file (e.g., `update_email.yaml`):

```yaml
subject: "New Features Available!"
body_html: |
  <h1>Check out our latest updates!</h1>
  <p>We've added some exciting new features...</p>
screenshots:
  - "screenshots/feature1.png"
test_mode: true
```

### 2. Test Mode (Preview)

Always test first! Set `test_mode: true`:

```bash
uv run python app/scripts/send_update_email.py update_email.yaml
```

This sends the email only to the configured test user (`TEST_EMAIL_RECIPIENT`).

### 3. Production Send

After verifying the test email looks correct, update config:

```yaml
test_mode: false  # Send to all users
```

Then run again:

```bash
uv run python app/scripts/send_update_email.py update_email.yaml
```

## Config File Format

### Required Fields

- `subject`: Email subject line (1-200 characters)
- `body_html`: HTML email body content
- `test_mode`: Boolean - `true` for test, `false` for production

### Optional Fields

- `screenshots`: List of image file paths (relative or absolute)
- `batch_size`: Emails per batch (default: 14, range: 1-100)
- `batch_delay_seconds`: Delay between batches (default: 1.0)

### Example Config

```yaml
subject: "Exciting New Features!"
body_html: |
  <div style="font-family: Arial, sans-serif;">
    <h1>What's New</h1>
    <p>We've added:</p>
    <ul>
      <li>Feature A</li>
      <li>Feature B</li>
    </ul>
  </div>
screenshots:
  - "screenshots/dashboard.png"
  - "screenshots/analytics.jpg"
test_mode: false
batch_size: 14
batch_delay_seconds: 1.0
```

## Screenshots

### Adding Screenshots

1. Place screenshot files in a directory (e.g., `screenshots/`)
2. Reference them in config:

```yaml
screenshots:
  - "screenshots/feature1.png"
  - "/absolute/path/to/feature2.jpg"
```

### Supported Formats

- PNG (`.png`)
- JPEG (`.jpg`, `.jpeg`)
- GIF (`.gif`)

### Best Practices

- Use relative paths when possible (easier to share/config)
- Keep file sizes reasonable (< 5MB per image)
- Maximum 10 screenshots per email
- Images are embedded inline in the email body

## HTML Email Body

### Writing HTML

Write HTML directly in the `body_html` field:

```yaml
body_html: |
  <h1>Title</h1>
  <p>Content here</p>
```

### Best Practices

- Use inline CSS (email clients have limited CSS support)
- Use table-based layouts for complex designs
- Test in Gmail, Outlook, Apple Mail
- Keep it simple - avoid modern CSS features

### Example Template

```yaml
body_html: |
  <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
    <h1 style="color: #333;">Title</h1>
    <p style="color: #666;">Content here</p>
    <a href="https://alexstocks.com" style="color: #007bff;">Visit Site</a>
  </div>
```

## Rate Limiting

The script automatically batches emails to respect AWS SES rate limits:

- **Default**: 14 emails per batch, 1 second delay between batches
- **Configurable**: Adjust `batch_size` and `batch_delay_seconds` in config

For large lists (1000+ users), the script will take time to complete. Progress is logged after each batch.

## Output

### Success Output

```
✅ Loading config file...
✅ Initializing services...
⚠️  WARNING: test_mode is False - this will send to ALL users!
Type 'yes' to confirm: yes
📧 Sending update emails...
   Mode: PRODUCTION (sending to 1,234 users)
   Estimated batches: 89
   Estimated time: 88 seconds
✅ Batch 1/89: Processing 14 emails (Elapsed: 2.1s, Est. remaining: 88s)
✅ Batch 2/89: Processing 14 emails (Elapsed: 3.2s, Est. remaining: 87s)
...
✅ All emails processed!
📊 Summary:
   - Total recipients: 1,234
   - Successful: 1,234
   - Failed: 0
   - Elapsed time: 92.45 seconds
```

### Error Output

```
❌ Config validation failed:
   - subject: cannot be empty
   - screenshots[0]: file not found: screenshots/missing.png
```

## Safety Features

1. **Test Mode Default**: Always test first with `test_mode: true`
2. **Confirmation Prompt**: Script requires explicit "yes" confirmation when `test_mode: false`
3. **Config Validation**: Script validates config before sending any emails
4. **User Filtering**: Automatically excludes:
   - Soft-deleted users
   - Users with bounced emails
   - Users with unverified emails
5. **Error Handling**: Continues sending even if some emails fail
6. **Summary Report**: Shows success/failure counts at the end
7. **Progress Indicators**: Shows batch progress and estimated time remaining

## Troubleshooting

### "No eligible users found"

- Check database connection
- Verify users exist and have verified email addresses
- Check `UserNotificationChannel` records

### "Screenshot file not found"

- Verify file paths are correct (relative to script execution directory)
- Check file permissions (must be readable)
- Use absolute paths if relative paths don't work

### "Email send failed"

- Check AWS SES configuration
- Verify `EMAIL_FROM_ADDRESS` is configured
- Check AWS credentials/permissions
- Review email service logs

### Rate Limit Errors

- Reduce `batch_size` in config
- Increase `batch_delay_seconds`
- Check AWS SES account limits

## Advanced Usage

### Auto-Generate Content

Generate draft email content from recent feature implementations:

```bash
# Generate config from last 30 days of features
uv run python app/scripts/send_update_email.py --auto-generate

# Generate and save to file
uv run python app/scripts/send_update_email.py --auto-generate --output draft.yaml

# Generate from last 7 days
uv run python app/scripts/send_update_email.py --auto-generate --days-back 7
```

The auto-generated config includes:
- Subject line based on number of features
- HTML body summarizing recent features
- Test mode enabled by default (for safety)

**Note**: Always review and edit the generated content before sending!

### Custom Batch Settings

```yaml
batch_size: 10
batch_delay_seconds: 2.0
```

### JSON Config (Alternative)

Script also supports JSON config files:

```json
{
  "subject": "New Features!",
  "body_html": "<p>Content</p>",
  "test_mode": true
}
```

### Example Config Files

See `specs/002-user-update-emails/examples/` for:
- `minimal.yaml` - Simplest config (test mode)
- `full.yaml` - Complete config with screenshots
- `auto-generated-template.yaml` - Example of auto-generated content

## See Also

- [Config Schema](../contracts/config-schema.yaml) - Full schema definition
- [Data Model](./data-model.md) - Data structures and validation
- [Research](./research.md) - Technical decisions and rationale

