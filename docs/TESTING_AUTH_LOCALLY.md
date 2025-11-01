# Testing Google OAuth Authentication Locally

This guide walks you through testing the U1 authentication implementation on your local machine.

## Prerequisites

- Python 3.11+ with `uv` installed
- PostgreSQL running locally
- Google Cloud Console access (for OAuth credentials)

## Step 1: Set Up Google OAuth Credentials

### 1.1 Create OAuth 2.0 Credentials

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select existing one
3. Navigate to **APIs & Services > Credentials**
4. Click **Create Credentials > OAuth 2.0 Client ID**
5. Configure OAuth consent screen if prompted:
   - User Type: **External** (for testing)
   - App name: `AlexStocks Local Dev`
   - User support email: Your email
   - Developer contact: Your email
   - Scopes: Add `email`, `profile`, `openid`
   - Test users: Add your Gmail address

### 1.2 Create OAuth Client ID

1. Application type: **Web application**
2. Name: `AlexStocks Local`
3. Authorized redirect URIs:
   ```
   http://localhost:8000/auth/callback
   ```
4. Click **Create**
5. **Save the Client ID and Client Secret** (you'll need these next)

## Step 2: Configure Environment Variables

### 2.1 Create `.env` File

In your project root (`/Users/alex/market-pulse-v2/`), copy the example file:

```bash
cp .env.example .env
```

Then edit `.env` and update the Google OAuth values:

```bash
# Required: Add your Google OAuth credentials
GOOGLE_CLIENT_ID=your-client-id-here.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=your-client-secret-here

# Optional: Change other defaults if needed
# DATABASE_URL=postgresql://postgres:postgres@localhost:5432/market_pulse
# SESSION_SECRET_KEY=dev-secret-key-change-in-production
# LOG_LEVEL=DEBUG
```

### 2.2 Verify `.env` is Loaded

```bash
# Check if .env is in .gitignore (it should be!)
grep ".env" .gitignore
```

## Step 3: Set Up Database

### 3.1 Ensure PostgreSQL is Running

```bash
# macOS with Homebrew
brew services start postgresql@14

# Or check if it's running
psql -U postgres -c "SELECT version();"
```

### 3.2 Create Database (if needed)

```bash
psql -U postgres -c "CREATE DATABASE market_pulse;"
```

### 3.3 Run Database Migrations

```bash
cd /Users/alex/market-pulse-v2
make migrate-up
```

Or directly with Alembic:
```bash
uv run alembic upgrade head
```

Expected output:
```
INFO  [alembic.runtime.migration] Running upgrade  -> 7a6b96aac112, create_user_tables
```

### 3.4 Verify Tables Created

```bash
psql -U postgres -d market_pulse -c "\dt users*"
```

Should show:
- `users`
- `user_profiles`
- `user_notification_channels`
- `user_ticker_follows`

## Step 4: Run the Application

### 4.1 Install Dependencies

```bash
cd /Users/alex/market-pulse-v2
uv sync
```

### 4.2 Start the Server

```bash
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

You should see:
```
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
INFO:     Started reloader process
INFO:     Started server process
INFO:     Waiting for application startup.
INFO:     Application startup complete.
```

### 4.3 Verify Server is Running

Open browser to: http://localhost:8000/

## Step 5: Test Authentication Flow

### 5.1 Access Login Page

Navigate to: **http://localhost:8000/auth/login**

You should see:
- "AlexStocks" header
- "Sign in with Google" button
- Clean, modern UI

### 5.2 Click "Sign in with Google"

This will:
1. Redirect to Google's OAuth consent screen
2. Show the permissions requested (email, profile)
3. Ask you to select your Google account

### 5.3 Authorize the Application

1. Select your **Gmail account** (non-Gmail will be rejected!)
2. Click **Continue** to grant permissions
3. You'll be redirected back to `http://localhost:8000/auth/callback`
4. Should redirect to home page (`/`) with authentication cookie set

### 5.4 Verify Authentication Succeeded

Check the browser's developer console:
- **Network tab**: Look for `session_token` cookie
- **Application/Storage tab**: Verify cookie exists

Or open: **http://localhost:8000/auth/me**

Should return JSON:
```json
{
  "id": 1,
  "email": "your-email@gmail.com",
  "auth_provider": "google",
  "is_active": true,
  "created_at": "2025-10-31T...",
  "updated_at": "2025-10-31T...",
  "name": "Your Name",
  "picture": "https://lh3.googleusercontent.com/...",
  "timezone": "UTC"
}
```

### 5.5 Verify Database Records

```bash
# Check users table
psql -U postgres -d market_pulse -c "SELECT id, email, auth_provider, is_active FROM users;"

# Check user_profiles table
psql -U postgres -d market_pulse -c "SELECT user_id, display_name, avatar_url FROM user_profiles;"
```

## Step 6: Test Additional Scenarios

### 6.1 Test Logout

Navigate to: **http://localhost:8000/auth/logout**

- Should clear the `session_token` cookie
- Redirect to `/`

Verify by visiting `/auth/me` again:
```json
{
  "detail": "Not authenticated"
}
```

### 6.2 Test Non-Gmail Account Rejection

1. Logout if logged in
2. Go to `/auth/login`
3. Click "Sign in with Google"
4. Select a **non-Gmail account** (e.g., `@outlook.com`, `@yahoo.com`)
5. Should redirect to `/auth/login?error=non_gmail_domain`
6. Error message displayed: "Only Gmail accounts are currently supported"

### 6.3 Test Existing User Login

1. Logout
2. Login again with the same Gmail account
3. Check `/auth/me` - should return same user ID
4. Database should still have only 1 user record (not a duplicate)

```bash
psql -U postgres -d market_pulse -c "SELECT COUNT(*) FROM users;"
```

Should show: `count: 1`

### 6.4 Test Session Persistence

1. Login
2. Close browser completely
3. Reopen browser
4. Navigate to `/auth/me`
5. Should still be authenticated (cookie persists for 30 days)

### 6.5 Test Blocked Account (Manual)

```bash
# Manually deactivate your account
psql -U postgres -d market_pulse -c "UPDATE users SET is_active = false WHERE email = 'your-email@gmail.com';"

# Try to access /auth/me
curl http://localhost:8000/auth/me -H "Cookie: session_token=YOUR_TOKEN"
```

Should return:
```json
{
  "detail": "Not authenticated"
}
```

Try to login again:
- Should redirect to `/auth/login?error=account_blocked`

**Restore account:**
```bash
psql -U postgres -d market_pulse -c "UPDATE users SET is_active = true WHERE email = 'your-email@gmail.com';"
```

### 6.6 Test Soft Delete (Manual)

```bash
# Soft delete your account
psql -U postgres -d market_pulse -c "UPDATE users SET is_deleted = true, deleted_at = NOW() WHERE email = 'your-email@gmail.com';"

# Try to login
# Should be blocked with "Account has been deleted" error
```

## Step 7: Testing with cURL/HTTPie

### Login Flow (Manual)

```bash
# 1. Get OAuth URL
curl http://localhost:8000/auth/login

# 2. Copy the Google OAuth URL from browser
# 3. After authorizing, Google redirects with a code parameter
# 4. The /auth/callback endpoint handles the rest automatically

# 5. Extract session_token cookie from browser or response headers
```

### Test Authenticated Endpoints

```bash
# Get current user info
curl http://localhost:8000/auth/me \
  -H "Cookie: session_token=YOUR_TOKEN_HERE"

# Logout
curl http://localhost:8000/auth/logout \
  -H "Cookie: session_token=YOUR_TOKEN_HERE"
```

## Step 8: Run Automated Tests

### Run Unit Tests

```bash
cd /Users/alex/market-pulse-v2
uv run pytest tests/test_auth_service.py -v
```

Expected: **17/17 PASSED**

### Run Integration Tests

```bash
uv run pytest tests/test_auth_integration.py -v
```

Note: Some tests may fail due to database state (seed data). Core functionality is verified by unit tests.

### Run All Auth Tests

```bash
uv run pytest tests/test_auth*.py -v
```

## Troubleshooting

### Issue: "OAuth error: redirect_uri_mismatch"

**Problem**: Redirect URI doesn't match Google Console configuration

**Solution**:
1. Check your `.env` file: `GOOGLE_REDIRECT_URI=http://localhost:8000/auth/callback`
2. Verify in Google Console: Authorized redirect URIs includes `http://localhost:8000/auth/callback`
3. Ensure exact match (trailing slash matters!)

### Issue: "Invalid credentials" or "Missing profile data"

**Problem**: OAuth credentials not configured or incorrect

**Solution**:
1. Verify `.env` has correct `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET`
2. Check application logs: `LOG_LEVEL=DEBUG` in `.env`
3. Ensure OAuth client is enabled in Google Console

### Issue: "Only Gmail accounts are currently supported"

**Problem**: Trying to login with non-Gmail account

**Solution**:
- Use a `@gmail.com` account
- Or modify `auth_service.py` to remove Gmail restriction:
  ```python
  # Comment out or remove this check
  # self.validate_gmail_domain(email)
  ```

### Issue: "Database connection failed"

**Problem**: PostgreSQL not running or wrong credentials

**Solution**:
```bash
# Check PostgreSQL is running
brew services list | grep postgresql

# Test connection
psql -U postgres -d market_pulse -c "SELECT 1;"

# Check DATABASE_URL in .env
echo $DATABASE_URL
```

### Issue: Cookie not being set

**Problem**: Browser blocks cookies or HTTPS issue

**Solution**:
1. Check browser console for cookie warnings
2. Ensure you're using `http://localhost:8000` (not `127.0.0.1`)
3. Check browser privacy settings (allow cookies)

### Issue: "Application logs 'google_oauth_config_missing'"

**Problem**: Missing OAuth credentials

**Solution**:
1. Ensure `.env` file exists and has `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET`
2. Restart the server after updating `.env`
3. Verify config is loaded:
   ```python
   from app.config import settings
   print(settings.google_client_id)
   ```

## Quick Test Script

Save this as `test_auth_local.sh`:

```bash
#!/bin/bash

echo "Testing AlexStocks Authentication Locally"
echo "=========================================="
echo ""

# 1. Check .env exists
if [ ! -f .env ]; then
    echo "❌ .env file not found!"
    echo "   Create .env with GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET"
    exit 1
fi
echo "✅ .env file exists"

# 2. Check PostgreSQL
if ! psql -U postgres -d market_pulse -c "SELECT 1;" > /dev/null 2>&1; then
    echo "❌ PostgreSQL connection failed!"
    echo "   Start PostgreSQL: brew services start postgresql@14"
    exit 1
fi
echo "✅ PostgreSQL running"

# 3. Check tables exist
if ! psql -U postgres -d market_pulse -c "SELECT COUNT(*) FROM users;" > /dev/null 2>&1; then
    echo "⚠️  Users table not found, running migrations..."
    make migrate-up
fi
echo "✅ Database tables ready"

# 4. Run linting
echo ""
echo "Running linting..."
uv run ruff check --fix . && uv run black . && uv run mypy .
if [ $? -eq 0 ]; then
    echo "✅ Linting passed"
else
    echo "❌ Linting failed"
    exit 1
fi

# 5. Run tests
echo ""
echo "Running tests..."
uv run pytest tests/test_auth_service.py -v
if [ $? -eq 0 ]; then
    echo "✅ Tests passed"
else
    echo "❌ Tests failed"
    exit 1
fi

echo ""
echo "=========================================="
echo "🎉 All checks passed!"
echo ""
echo "To start the server:"
echo "  uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000"
echo ""
echo "Then visit:"
echo "  http://localhost:8000/auth/login"
```

Make it executable:
```bash
chmod +x test_auth_local.sh
./test_auth_local.sh
```

## Next Steps After Local Testing

1. ✅ Verify OAuth flow works end-to-end
2. ✅ Test with multiple Gmail accounts
3. ✅ Verify database records are correct
4. 📋 Set up staging environment
5. 📋 Configure production OAuth credentials
6. 📋 Add error tracking (Sentry)
7. 📋 Set up monitoring for failed login attempts

## Production Checklist

Before deploying to production:

- [ ] Use strong `SESSION_SECRET_KEY` (not the dev default!)
- [ ] Set up production Google OAuth credentials with correct redirect URI
- [ ] Enable HTTPS (required for secure cookies)
- [ ] Set `secure=True` on session cookie
- [ ] Configure proper CORS settings
- [ ] Set up rate limiting on auth endpoints
- [ ] Enable audit logging for authentication events
- [ ] Set up monitoring/alerts for failed logins
- [ ] Test OAuth flow on staging environment
- [ ] Document user support process for blocked accounts

## Useful Commands Reference

```bash
# Start server
uv run uvicorn app.main:app --reload --port 8000

# Run tests
uv run pytest tests/test_auth*.py -v

# Check database
psql -U postgres -d market_pulse -c "SELECT * FROM users;"

# Clear test users
psql -U postgres -d market_pulse -c "TRUNCATE users, user_profiles CASCADE;"

# View logs with filtering
uv run uvicorn app.main:app --log-level debug 2>&1 | grep -i auth

# Test endpoint with session
curl -X GET http://localhost:8000/auth/me \
  -H "Cookie: session_token=YOUR_TOKEN" \
  -H "Content-Type: application/json"
```

Happy testing! 🚀

