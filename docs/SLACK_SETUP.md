# Slack Integration Setup Guide

This guide walks through setting up Slack notifications for job lifecycle events and user registration.

## Overview

The Slack integration provides:
- **Job lifecycle notifications**: Start and completion messages for all jobs
- **Job summaries**: Metrics like duration, success/failure counts, and custom stats
- **User registration alerts**: Notifications when new users first log in
- **Error reporting**: Automatic error messages in completion notifications

## Architecture

- **EC2 (Main App)**: FastAPI app sends user registration notifications
- **ECS Fargate (Jobs)**: Containerized jobs send lifecycle notifications
- **Slack Service**: Simple service (`app/services/slack_service.py`) handles all Slack API calls
- **Job Wrapper**: Simple wrapper function (`jobs/jobs/slack_wrapper.py`) wraps job execution

## Step 1: Create Slack App

1. Go to https://api.slack.com/apps
2. Click **"Create New App"** → **"From scratch"**
3. Enter app name: `Market Pulse Admin` (or your preferred name)
4. Select your workspace
5. Click **"Create App"**

## Step 2: Configure Bot Token Scopes

1. In your app settings, go to **"OAuth & Permissions"** in the left sidebar
2. Scroll to **"Bot Token Scopes"**
3. Add the following scope:
   - `chat:write` - Send messages to channels

4. Scroll up and click **"Install to Workspace"**
5. Authorize the app
6. Copy the **"Bot User OAuth Token"** (starts with `xoxb-`)

## Step 3: Create Slack Channels

Create channels for notifications:

- **`#market-pulse-jobs`** - For all job notifications (default)
- **`#market-pulse-users`** - For new user registrations (optional, falls back to default)

You can also create dedicated channels per job if desired (future enhancement).

## Step 4: Invite Bot to Channels

1. Open each channel in Slack
2. Type: `/invite @Market Pulse Admin` (use your bot name)
3. Or use channel settings → **Integrations** → **Add apps**

## Step 5: Get Channel IDs

Channel IDs are required for configuration. Find them:

1. Open Slack in a web browser
2. Navigate to the channel
3. Look at the URL: `https://yourworkspace.slack.com/archives/C1234567890`
4. The channel ID is `C1234567890` (the part after `/archives/`)

For private channels, use the same URL format.

## Step 6: Configure AWS Secrets Manager

Store Slack credentials in AWS Secrets Manager for ECS tasks:

```bash
# Bot token
aws secretsmanager create-secret \
  --name market-pulse/slack-bot-token \
  --secret-string "xoxb-your-bot-token-here" \
  --region us-east-1

# Default channel (for jobs)
aws secretsmanager create-secret \
  --name market-pulse/slack-default-channel \
  --secret-string "C1234567890" \
  --region us-east-1

# Users channel (optional, falls back to default if not set)
aws secretsmanager create-secret \
  --name market-pulse/slack-users-channel \
  --secret-string "C4444444444" \
  --region us-east-1
```

## Step 7: Configure EC2 (Main App)

For the EC2 instance running the FastAPI app, add environment variables:

### Option A: Environment Variables

Add to `/etc/environment` or your `.env` file:

```bash
SLACK_BOT_TOKEN=xoxb-your-token-here
SLACK_DEFAULT_CHANNEL=C1234567890
SLACK_USERS_CHANNEL=C4444444444
```

### Option B: Systemd Service File

If using systemd, add to `/etc/systemd/system/market-pulse-api.service`:

```ini
[Service]
Environment="SLACK_BOT_TOKEN=xoxb-..."
Environment="SLACK_DEFAULT_CHANNEL=C1234567890"
Environment="SLACK_USERS_CHANNEL=C4444444444"
```

Then reload: `sudo systemctl daemon-reload && sudo systemctl restart market-pulse-api`

## Step 8: Update Terraform Configuration

The Terraform configuration in `infrastructure/terraform/secrets.tf` already includes Slack secret data sources. These are automatically wired into ECS task definitions in `ecs.tf`.

To deploy:

```bash
cd infrastructure/terraform
terraform apply
```

This updates all ECS task definitions to include Slack secrets.

## Step 9: Deploy

1. **Update ECS task definitions:**
   ```bash
   cd infrastructure/terraform
   terraform apply
   ```

2. **Restart EC2 app** (if using environment variables):
   ```bash
   sudo systemctl restart market-pulse-api
   # Or however you restart your app
   ```

3. **Redeploy ECS jobs** (if Docker image changed):
   ```bash
   make push-jobs-image
   ```

## Step 10: Test

### Test Job Notification

Trigger a job manually:

```bash
# From EC2 or ECS
python jobs/jobs/collect_stock_prices.py --type current
```

You should see:
1. **Start notification** in Slack with job name, environment, and metadata
2. **Completion notification** with status, duration, and summary (threaded)

### Test User Registration

Create a test user account through the OAuth flow. You should receive a notification in the users channel (or default channel) with:
- User email and display name
- User ID
- Total user count
- Environment tag

## How It Works

### Job Notifications

Jobs use the `run_with_slack()` wrapper:

```python
from jobs.jobs.slack_wrapper import run_with_slack

def run_job():
    # Your job code
    return {"success": 100, "failed": 5}  # Optional: return stats dict

run_with_slack(
    job_name="my_job",
    job_func=run_job,
    metadata={"key": "value"},  # Optional
)
```

The wrapper:
1. Sends start notification
2. Executes your job function
3. Sends completion notification (with summary if job returns a dict)
4. Handles errors and includes them in completion message

### User Notifications

User notifications are automatically sent when `AuthService.get_or_create_user()` creates a new user. No code changes needed - it's already integrated.

## Configuration Reference

### Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `SLACK_BOT_TOKEN` | Yes | Bot User OAuth Token (xoxb-...) |
| `SLACK_DEFAULT_CHANNEL` | Yes | Default channel ID for jobs |
| `SLACK_USERS_CHANNEL` | No | Channel for user notifications (defaults to SLACK_DEFAULT_CHANNEL) |

### Job Names

Job names used in notifications:
- `collect_stock_prices` - Stock price collection (current)
- `collect_stock_prices_historical` - Historical stock data
- `analyze_sentiment` - Sentiment analysis job
- `reddit_scraper` - Reddit incremental scraping
- `reddit_scraper_backfill` - Reddit historical backfill

## Troubleshooting

### No Notifications Appearing

1. **Check bot token:**
   ```bash
   curl -X POST https://slack.com/api/auth.test \
     -H "Authorization: Bearer xoxb-your-token" \
     -H "Content-Type: application/json"
   ```

2. **Verify bot is in channel:**
   - Check channel members list
   - Bot must be invited to channel

3. **Check environment variables:**
   ```bash
   # On EC2
   echo $SLACK_BOT_TOKEN
   echo $SLACK_DEFAULT_CHANNEL
   ```

4. **Check ECS task secrets:**
   ```bash
   aws ecs describe-task-definition \
     --task-definition market-pulse-reddit-scraper \
     --query 'taskDefinition.containerDefinitions[0].secrets'
   ```

5. **Check application logs:**
   - Look for "Slack bot token not configured" (means token is missing)
   - Look for "Slack API error" (means API call failed)

### Wrong Channel

- Verify channel IDs are correct (they change if channel is renamed)
- Check `SLACK_DEFAULT_CHANNEL` and `SLACK_USERS_CHANNEL` environment variables

### Notifications Not Threading

Threading requires capturing the thread timestamp from the start message. The current implementation captures this automatically, but if threading isn't working, check that:
- Start notification succeeds (returns a timestamp)
- Completion notification uses the same `thread_ts`

## Security Best Practices

1. **Never commit tokens to git** - Use Secrets Manager or environment variables
2. **Rotate tokens regularly** - Regenerate in Slack app settings
3. **Use private channels** - For sensitive job notifications
4. **Limit bot permissions** - Only grant `chat:write` scope
5. **Monitor usage** - Check Slack API usage in app dashboard

## Future Enhancements

- Per-job channel mapping (JSON config)
- Log streaming to Slack threads
- Configurable log level thresholds
- CloudWatch log links in notifications
- Interactive Slack commands for job control

## Support

For issues:
1. Check application logs: `make ecs-logs-<job-name>` or EC2 logs
2. Review Slack API logs in app dashboard
3. Test with `curl` commands above
4. Verify channel IDs and permissions

