# Timezone Detection Feature

## Overview

AlexStocks now automatically detects and stores each user's timezone from their browser, providing a more personalized experience.

## How It Works

### 1. Detection on Login Page
When a user clicks "Sign in with Google":
```javascript
// Detects timezone using browser API
const userTimeZone = Intl.DateTimeFormat().resolvedOptions().timeZone;
// Returns: "Asia/Jerusalem", "America/New_York", "Europe/London", etc.

// Stores in localStorage for use after OAuth redirect
localStorage.setItem('user_timezone', userTimeZone);
```

### 2. Automatic Update After Login
After successful login, the timezone is automatically sent to the server:
```javascript
// Runs on every page load if user is logged in
POST /auth/update-timezone
Body: { "timezone": "Asia/Jerusalem" }
```

The system only updates if the detected timezone differs from the stored one, minimizing unnecessary database writes.

### 3. Storage in Database
User timezone is stored in the `user_profiles` table:
```sql
user_profiles
  user_id: 1
  timezone: "Asia/Jerusalem"  -- Automatically detected
  display_name: "Alex Kremiansky"
  avatar_url: "https://..."
```

## Why Not from Google OAuth?

**Google OAuth does NOT provide timezone information.** The only way to get accurate timezone is from the user's browser, which reflects their actual system settings.

## API Endpoints

### GET `/auth/me`
Returns user profile including timezone:
```json
{
  "id": 1,
  "email": "alex@gmail.com",
  "timezone": "Asia/Jerusalem",
  "name": "Alex Kremiansky",
  ...
}
```

### POST `/auth/update-timezone`
Updates user's timezone (called automatically by frontend):
```bash
curl -X POST http://localhost:8000/auth/update-timezone \
  -H "Content-Type: application/json" \
  -H "Cookie: session_token=..." \
  -d '{"timezone": "Asia/Jerusalem"}'
```

Response:
```json
{
  "success": true,
  "timezone": "Asia/Jerusalem"
}
```

## User Experience

### First Login
1. User clicks "Sign in with Google"
2. Browser detects timezone → "Asia/Jerusalem"
3. Stored in localStorage
4. OAuth flow completes → User logged in
5. Page loads → Timezone sent to server
6. Profile updated with "Asia/Jerusalem"

### Subsequent Visits
1. User visits site
2. System checks: stored timezone vs profile timezone
3. If different → Update profile
4. If same → No action needed

### Timezone Changes
If a user travels or changes their system timezone:
- On next page load, the system detects the new timezone
- Automatically updates the profile
- No user action required

## Use Cases

### Current Implementation
- Stored in user profile for future use
- Returned in `/auth/me` endpoint
- Available for any backend logic that needs timezone

### Future Enhancements
1. **Localized Timestamps**: Show article times in user's timezone
   ```
   Instead of: "Published at 14:00 UTC"
   Show: "Published at 17:00 IST" (for Israel user)
   ```

2. **Market Hours**: Show relevant market hours based on user location
   ```
   Israel user: "NASDAQ opens in 4 hours (16:30 your time)"
   ```

3. **Notification Scheduling**: Send notifications at appropriate local times
   ```
   Send morning digest at 8:00 AM user's local time
   ```

4. **Analytics**: Track user distribution by timezone

## Technical Details

### Browser Timezone Detection
Uses the `Intl.DateTimeFormat` API (supported by all modern browsers):
```javascript
Intl.DateTimeFormat().resolvedOptions().timeZone
```

Returns IANA timezone names:
- `Asia/Jerusalem` (Israel)
- `America/New_York` (US Eastern)
- `Europe/London` (UK)
- `Asia/Tokyo` (Japan)
- etc.

### Default Timezone
If timezone detection fails or user hasn't logged in yet:
- Default: `"UTC"`
- Safe fallback that works globally

### Data Privacy
- Timezone is considered non-sensitive information
- Used only for improving user experience
- Not shared with third parties
- User can't manually change it (automatically detected)

## Code Locations

### Frontend
- **Login page**: `app/templates/auth/login.html` (lines 67-81)
  - Detects timezone on button click
  - Stores in localStorage

- **Base template**: `app/templates/base.html` (lines 468-506)
  - Auto-updates timezone after login
  - Runs on every page load

### Backend
- **API route**: `app/api/routes/auth.py`
  - `POST /auth/update-timezone` (lines 231-273)
  - Updates user profile timezone

- **Database**: `app/db/models.py`
  - `UserProfile.timezone` field (String(50))
  - Default: "UTC"

## Testing

### Manual Testing

1. **Test timezone detection**:
   ```javascript
   // Open browser console on login page
   console.log(Intl.DateTimeFormat().resolvedOptions().timeZone);
   // Should show your timezone (e.g., "Asia/Jerusalem")
   ```

2. **Test login flow**:
   ```bash
   # Login and check your timezone
   curl http://localhost:8000/auth/me -H "Cookie: session_token=..."
   # Should show your detected timezone
   ```

3. **Test manual update**:
   ```bash
   curl -X POST http://localhost:8000/auth/update-timezone \
     -H "Content-Type: application/json" \
     -H "Cookie: session_token=..." \
     -d '{"timezone": "America/Los_Angeles"}'
   ```

### Automated Testing
Add tests for the `/auth/update-timezone` endpoint:
```python
def test_update_timezone(client, authenticated_user):
    response = client.post(
        "/auth/update-timezone",
        json={"timezone": "Asia/Jerusalem"},
        cookies={"session_token": authenticated_user.session_token}
    )
    assert response.status_code == 200
    assert response.json()["timezone"] == "Asia/Jerusalem"
```

## Security Considerations

### Input Validation
Currently accepts any string as timezone. Consider adding validation:
```python
# List of valid IANA timezones
import pytz

def validate_timezone(timezone: str) -> bool:
    return timezone in pytz.all_timezones
```

### Authentication Required
- Endpoint requires valid session token
- Can only update your own timezone
- No way to change other users' timezones

### Rate Limiting
Consider rate limiting the `/auth/update-timezone` endpoint to prevent abuse:
```python
# Limit to 10 updates per hour per user
@limiter.limit("10/hour")
@router.post("/update-timezone")
async def update_timezone(...):
    ...
```

## Troubleshooting

### Issue: Timezone shows "UTC" instead of my timezone

**Cause**: Timezone not detected or not sent to server

**Solutions**:
1. Check browser console for errors
2. Verify localStorage has `user_timezone`:
   ```javascript
   localStorage.getItem('user_timezone')
   ```
3. Check network tab for `/auth/update-timezone` request
4. Try logging out and logging in again

### Issue: Timezone doesn't update after traveling

**Cause**: Browser cached the old timezone

**Solutions**:
1. Hard refresh the page (Cmd+Shift+R / Ctrl+Shift+R)
2. Clear localStorage:
   ```javascript
   localStorage.removeItem('user_timezone')
   ```
3. Log out and log in again

### Issue: Server logs show timezone update errors

**Cause**: Invalid timezone format or database issue

**Solutions**:
1. Check server logs for specific error
2. Verify user profile exists in database
3. Check database connection

## Future Improvements

1. **Validation**: Add IANA timezone validation
2. **Manual Override**: Allow users to manually set timezone in settings
3. **Timezone History**: Track timezone changes for analytics
4. **Smart Detection**: Detect timezone changes even without login/logout
5. **Fallback**: Use IP-based geolocation as fallback if browser detection fails

## References

- [IANA Time Zone Database](https://www.iana.org/time-zones)
- [MDN: Intl.DateTimeFormat](https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Intl/DateTimeFormat)
- [Python pytz Documentation](https://pythonhosted.org/pytz/)

---

**Status**: ✅ Implemented and Active

**Version**: Added in PR #61 (U1 Authentication)

**Last Updated**: October 31, 2025

