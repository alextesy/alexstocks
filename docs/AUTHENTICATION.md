# Authentication System - Google OAuth

This document describes the Google OAuth authentication implementation for AlexStocks.

## Overview

The authentication system uses Google OAuth 2.0 to authenticate users with Gmail accounts. Upon successful authentication, users receive a JWT session token stored in a secure HTTP-only cookie.

## Features

- ✅ **Gmail-only OAuth**: Currently restricted to Gmail accounts (@gmail.com)
- ✅ **Secure sessions**: JWT tokens with configurable expiration (default: 30 days)
- ✅ **User provisioning**: Automatic user creation on first login
- ✅ **Account blocking**: Support for blocking/deactivating user accounts
- ✅ **Refresh tokens**: Optional storage of OAuth refresh tokens
- ✅ **Structured logging**: All auth events logged with context

## Architecture

### Components

1. **Database Model** (`app/db/models.py`)
   - `User` model with Google ID, email, profile info
   - Indexes on email, google_id, and last_login_at

2. **Auth Service** (`app/services/auth_service.py`)
   - OAuth code exchange
   - User info retrieval from Google
   - Gmail domain validation
   - User provisioning (get or create)
   - JWT token generation and verification

3. **API Routes** (`app/api/routes/auth.py`)
   - `GET /auth/login` - Login page with Google Sign-In
   - `GET /auth/callback` - OAuth callback handler
   - `GET /auth/logout` - Logout endpoint
   - `GET /auth/me` - Get current user info

4. **Templates** (`app/templates/auth/`)
   - `login.html` - Login page with Google OAuth button
   - User menu in `base.html` navigation

## Configuration

Add these environment variables to your `.env` file:

```bash
# Google OAuth Configuration
GOOGLE_CLIENT_ID=your-google-client-id.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=your-google-client-secret
GOOGLE_REDIRECT_URI=http://localhost:8000/auth/callback

# Session Configuration
SESSION_SECRET_KEY=your-secret-key-change-in-production
```

### Getting Google OAuth Credentials

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select existing one
3. Enable the Google+ API
4. Go to "Credentials" → "Create Credentials" → "OAuth 2.0 Client ID"
5. Configure OAuth consent screen
6. Add authorized redirect URIs:
   - Development: `http://localhost:8000/auth/callback`
   - Production: `https://yourdomain.com/auth/callback`
7. Copy the Client ID and Client Secret

## Database Migration

Run the migration script to add the users table:

```bash
uv run python app/scripts/add_users_table.py
```

Or use Alembic:

```bash
uv run alembic revision --autogenerate -m "Add users table"
uv run alembic upgrade head
```

## Usage

### Login Flow

1. User clicks "Sign In" in navigation
2. Redirected to `/auth/login` page
3. Clicks "Sign in with Google" button
4. Google OAuth consent screen
5. Redirected to `/auth/callback?code=...`
6. Backend:
   - Exchanges code for access token
   - Retrieves user info from Google
   - Validates Gmail domain
   - Creates/updates user record
   - Issues JWT session token
7. User redirected to home page with session cookie

### Protected Routes

To protect a route, check for valid session:

```python
from fastapi import Cookie, HTTPException, Depends
from app.services.auth_service import get_auth_service
from app.db.session import get_db

async def get_current_user(
    session_token: str | None = Cookie(None),
    db: Session = Depends(get_db)
):
    if not session_token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    auth_service = get_auth_service()
    user = auth_service.get_current_user(db, session_token)
    
    if not user:
        raise HTTPException(status_code=401, detail="Invalid session")
    
    return user

@app.get("/protected")
async def protected_route(user: User = Depends(get_current_user)):
    return {"message": f"Hello, {user.name}!"}
```

### Client-side: Check Auth Status

The base template automatically loads user info via JavaScript:

```javascript
// User menu is automatically populated
// Check /auth/me endpoint to verify authentication
fetch('/auth/me', { credentials: 'same-origin' })
  .then(response => response.json())
  .then(user => console.log('Logged in as:', user.email))
  .catch(() => console.log('Not logged in'));
```

## Error Handling

The system handles various error cases:

| Error | Redirect | Description |
|-------|----------|-------------|
| `non_gmail` | `/auth/login?error=non_gmail` | User tried to login with non-Gmail account |
| `account_blocked` | `/auth/login?error=account_blocked` | User account is inactive |
| `missing_data` | `/auth/login?error=missing_data` | Required profile data missing |
| `auth_failed` | `/auth/login?error=auth_failed` | Generic authentication failure |
| `oauth_error` | `/auth/login?error=oauth_error` | Error from OAuth provider |

## Security Considerations

1. **HTTPS in Production**: Always use HTTPS in production for secure cookies
2. **Secret Key**: Use a strong, random SESSION_SECRET_KEY (min 32 chars)
3. **Cookie Settings**:
   - `httponly=True`: Prevents JavaScript access
   - `secure=True` (production): HTTPS only
   - `samesite="lax"`: CSRF protection
4. **Token Expiration**: Default 30 days, configurable via `session_max_age_seconds`
5. **Gmail Domain**: Enforced at backend, configurable for future expansion
6. **Refresh Tokens**: Stored encrypted in database (optional)

## Testing

### Unit Tests

```bash
uv run pytest tests/test_auth_service.py -v
```

Tests cover:
- OAuth URL generation
- Token exchange
- User info retrieval
- Gmail domain validation
- User provisioning
- JWT token creation/verification
- Session management

### Integration Tests

```bash
uv run pytest tests/test_auth_integration.py -v
```

Tests cover:
- Login page rendering
- OAuth callback flow (new user)
- OAuth callback flow (existing user)
- Non-Gmail rejection
- Blocked account handling
- Logout
- `/auth/me` endpoint

## Logging

All authentication events are logged with structured context:

```python
logger.info("user_logged_in", extra={"user_id": user.id, "email": user.email})
logger.warning("non_gmail_login_attempt", extra={"email_domain": "yahoo.com"})
logger.error("oauth_callback_error", extra={"error": "invalid_grant"})
```

## Future Enhancements

- [ ] Support for additional OAuth providers (GitHub, Microsoft)
- [ ] Multi-factor authentication (MFA)
- [ ] Email domain whitelist configuration
- [ ] Session management dashboard
- [ ] Rate limiting for auth endpoints
- [ ] Remember device feature
- [ ] Account deletion/GDPR compliance

## Troubleshooting

### "Only Gmail accounts are supported"
- Check that user's email ends with @gmail.com
- Future: Configure allowed domains in settings

### OAuth Error: redirect_uri_mismatch
- Verify GOOGLE_REDIRECT_URI matches exactly in Google Console
- Include http/https, port, and path

### Invalid Session
- Token may be expired (check session_max_age_seconds)
- Secret key may have changed (invalidates all tokens)
- User account may be inactive

### Cookie Not Set
- Check browser console for errors
- Verify response sets Set-Cookie header
- In production, ensure HTTPS is enabled

## References

- [Google OAuth 2.0 Documentation](https://developers.google.com/identity/protocols/oauth2)
- [FastAPI Security](https://fastapi.tiangolo.com/tutorial/security/)
- [JWT Best Practices](https://tools.ietf.org/html/rfc8725)

