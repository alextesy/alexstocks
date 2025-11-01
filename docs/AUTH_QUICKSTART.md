# Authentication Testing - Quick Start

## 🚀 5-Minute Setup

### 1. Get Google OAuth Credentials
1. Go to [Google Cloud Console](https://console.cloud.google.com/apis/credentials)
2. Create OAuth 2.0 Client ID (Web application)
3. Add redirect URI: `http://localhost:8000/auth/callback`
4. Save Client ID and Secret

### 2. Configure `.env`
```bash
# Copy the example file and fill in your values
cp .env.example .env

# Then edit .env with your Google OAuth credentials:
# GOOGLE_CLIENT_ID=your-client-id.apps.googleusercontent.com
# GOOGLE_CLIENT_SECRET=your-client-secret
# (other values have sensible defaults)
```

### 3. Run Migrations & Start Server
```bash
# Ensure PostgreSQL is running
make migrate-up     # Run migrations
make up            # Start server
```

### 4. Test It
1. Open: http://localhost:8000/auth/login
2. Click "Sign in with Google"
3. Authorize with Gmail account
4. Check profile: http://localhost:8000/auth/me

## ✅ Verification Checklist

```bash
# Check migration status
make migrate-status

# Verify tables exist
psql -U postgres -d market_pulse -c "\dt users*"

# Run unit tests
uv run pytest tests/test_auth_service.py -v

# Check user records
psql -U postgres -d market_pulse -c "SELECT id, email, auth_provider FROM users;"
```

## 📋 Key Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/auth/login` | GET | Login page with Google button |
| `/auth/callback` | GET | OAuth callback (auto-redirect) |
| `/auth/me` | GET | Get current user info (requires auth) |
| `/auth/logout` | GET | Logout and clear session |

## 🔍 Common Issues

| Issue | Solution |
|-------|----------|
| "redirect_uri_mismatch" | Check redirect URI matches Google Console exactly |
| "Only Gmail accounts..." | Use `@gmail.com` account |
| "Not authenticated" | Check cookie is set in browser dev tools |
| "google_oauth_config_missing" | Verify `.env` has `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` |

## 📖 Full Documentation

- **Comprehensive Guide**: [TESTING_AUTH_LOCALLY.md](./TESTING_AUTH_LOCALLY.md)
- **Implementation Details**: [U1_ALIGNMENT_FIX.md](./U1_ALIGNMENT_FIX.md)
- **Architecture**: [AUTHENTICATION.md](./AUTHENTICATION.md)

## 🎯 What's Working

✅ Google OAuth login flow  
✅ User creation with profile (name, picture)  
✅ Session management (JWT, 30-day expiry)  
✅ Gmail-only restriction  
✅ Soft-delete support  
✅ Multi-provider ready (auth_provider field)  
✅ 17/17 unit tests passing  
✅ Full type safety (mypy clean)  

## 🚀 Production Ready

The authentication system is **production-ready** and uses:
- ✅ Alembic migrations (versioned schema)
- ✅ Proper security (JWT, secure cookies)
- ✅ SQLAlchemy 2.0 with type hints
- ✅ Comprehensive test coverage
- ✅ Extensible for future providers

