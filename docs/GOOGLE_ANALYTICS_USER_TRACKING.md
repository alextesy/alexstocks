# Google Analytics User Tracking

## Overview

AlexStocks now sends authenticated user data to Google Analytics, allowing you to track user behavior, retention, and engagement with GA4.

## ✅ What's Tracked

### 1. **User ID** 
- Unique identifier for each user
- Enables cross-device/session tracking
- Shows user journey across visits

### 2. **Login Events**
- Fires when user successfully logs in
- Method: "Google"
- Category: "authentication"

### 3. **Logout Events**
- Fires when user logs out
- Category: "authentication"

### 4. **User Properties**
- `timezone`: User's detected timezone (e.g., "Asia/Jerusalem")
- `auth_provider`: How they logged in ("google")
- `user_type`: "authenticated"

## 📊 What You'll See in Google Analytics

### In GA4 Dashboard

**User Explorer**:
- See individual user journeys
- Track returning users
- View user lifetime value

**Events**:
- `login` events with Google as method
- `logout` events
- All page views with user_id attached

**User Properties**:
- Segment users by timezone
- See how many are authenticated
- Track OAuth provider distribution

### Example Queries

**How many unique users logged in today?**
```
Events → login → Count unique users
```

**What's the distribution by timezone?**
```
User properties → timezone → Users
```

**Retention: How many users return after 7 days?**
```
Retention → User retention → 7-day cohort
```

## 🔧 Technical Implementation

### When Data is Sent

#### 1. On Login (Immediate)
```javascript
// After OAuth callback
gtag('event', 'login', {
    'method': 'Google',
    'event_category': 'authentication',
    'event_label': 'successful_login'
});
```

#### 2. On Every Page Load (for authenticated users)
```javascript
// Set user ID
gtag('config', 'GTM_CONTAINER_ID', {
    'user_id': userData.id
});

// Set user properties
gtag('set', 'user_properties', {
    'timezone': 'Asia/Jerusalem',
    'auth_provider': 'google',
    'user_type': 'authenticated'
});
```

#### 3. On Logout
```javascript
gtag('event', 'logout', {
    'event_category': 'authentication',
    'event_label': 'user_logout'
});
```

### Privacy & Consent

**Respects User Consent**:
- Only sends data if user accepts cookies
- Complies with GDPR/consent mode v2
- Users can opt out via cookie banner

**What's NOT sent**:
- Email addresses
- Names
- Any PII (Personally Identifiable Information)

**What IS sent**:
- User ID (numeric, non-identifiable)
- Timezone (general location indicator)
- Login method (just "Google")

## 🚀 Setup Required (One-Time)

### Step 1: Enable User-ID in GA4

1. Go to **[Google Analytics Admin](https://analytics.google.com/)**
2. Select your property
3. Navigate to **Data Settings > Data Collection**
4. Enable **User-ID** feature
5. Accept the terms

### Step 2: Verify in GA4

After deploying and logging in:

1. Go to **Reports > Real-time**
2. Login to your site
3. You should see:
   - User event with `login` 
   - User properties showing up
   - User ID attached to session

### Step 3: Create Custom Reports (Optional)

Create useful reports in GA4:

**Authenticated User Dashboard**:
```
Dimension: User ID
Metrics: Sessions, Page views, Engagement time
Filter: user_type = "authenticated"
```

**Login Funnel**:
```
Events: page_view (/auth/login) → login event → page_view (/)
```

**Timezone Distribution**:
```
Dimension: timezone (user property)
Metric: Active users
Visualization: Geo map or bar chart
```

## 📈 What You Can Now Analyze

### User Engagement
- **Daily Active Users** (DAU)
- **Weekly Active Users** (WAU)
- **Monthly Active Users** (MAU)
- **Session duration** for authenticated users
- **Pages per session**

### User Acquisition
- **New users** (first login)
- **Returning users**
- **User retention** (Day 1, 7, 30)

### User Behavior
- **Most visited pages** by authenticated users
- **User journey paths**
- **Drop-off points** in funnels
- **Feature adoption rates**

### Geographic Insights
- **Users by timezone**
- **Peak usage times** per region
- **Engagement by location**

## 🔍 Debugging

### Check if Data is Being Sent

**Browser Console (after login)**:
```javascript
// Should see these logs:
"Login event sent to Google Analytics"
"Timezone updated to: Asia/Jerusalem"
```

**GA4 DebugView**:
1. Install **[GA Debugger Chrome Extension](https://chrome.google.com/webstore)**
2. Enable it
3. Login to your site
4. Check GA4 **DebugView** in real-time

### Common Issues

**Issue: No user data in GA**

**Causes**:
1. GTM not configured in production
2. User hasn't accepted cookies
3. User-ID feature not enabled in GA4

**Solutions**:
```bash
# 1. Check environment
echo $ENV  # Should be "production"

# 2. Check GTM_CONTAINER_ID is set
echo $GTM_CONTAINER_ID  # Should be your GTM ID

# 3. Check browser console for errors
```

**Issue: User ID not showing in GA**

**Cause**: User-ID feature not enabled

**Solution**: Enable in GA4 Data Settings (see Setup Step 1)

## 📋 Configuration

### Environment Variables Required

```bash
# Production .env
ENV=production
GTM_CONTAINER_ID=GTM-XXXXXXX
COOKIE_CONSENT_ENABLED=true
```

### Optional Settings

```python
# app/config.py (already configured)
cookie_consent_enabled: bool = True  # Show cookie banner
environment: Literal["development", "staging", "production"] = "production"
```

## 🔐 Privacy Compliance

### GDPR Compliant
- ✅ Consent banner shown
- ✅ Opt-out available
- ✅ No PII collected
- ✅ Data minimization (only user_id, no email)

### What Users See
```
Cookie Banner:
"We use cookies to improve functionality and measure traffic. 
You can accept, reject, or customize."

[ ] Analytics  [ ] Ads
[Accept All] [Reject All] [Save Preferences]
```

### User Rights
- Users can **reject** analytics cookies
- Users can **customize** consent
- Consent saved in localStorage
- Can revoke at any time (via banner)

## 📊 Example Analytics Dashboard

Once set up, you can create a dashboard showing:

```
┌─────────────────────────────────────┐
│  Authenticated Users Overview       │
├─────────────────────────────────────┤
│ Today:      45 users                │
│ This Week:  234 users               │
│ This Month: 1,234 users             │
├─────────────────────────────────────┤
│ New Users:     23                   │
│ Returning:     22                   │
│ Retention (7d): 68%                 │
├─────────────────────────────────────┤
│ Top Timezones:                      │
│ 1. America/New_York    (34%)        │
│ 2. Europe/London       (28%)        │
│ 3. Asia/Jerusalem      (15%)        │
└─────────────────────────────────────┘
```

## 🎯 Next Steps

1. **Deploy** these changes to production
2. **Enable User-ID** in GA4 (one-time setup)
3. **Login** to verify events are firing
4. **Create custom reports** in GA4
5. **Monitor** user engagement over time

## 🚨 Important Notes

### Development vs Production

**Development** (localhost):
- GTM/GA **NOT loaded**
- Console logs only
- No data sent to GA

**Production** (alexstocks.com):
- GTM/GA **loaded**
- Events sent to GA
- User tracking active

### Testing in Production

To test without affecting real data:
1. Create a **test property** in GA4
2. Use that container ID for staging
3. Verify events before using production property

## 📚 Resources

- [GA4 User-ID Documentation](https://support.google.com/analytics/answer/9213390)
- [GTM Setup Guide](https://tagmanager.google.com/)
- [GA4 Events Reference](https://developers.google.com/analytics/devguides/collection/ga4/events)
- [GDPR Compliance Guide](https://support.google.com/analytics/answer/9019185)

---

**Status**: ✅ Implemented and Ready

**Requires**: GTM_CONTAINER_ID in production .env

**Privacy**: GDPR compliant, respects user consent

**Next**: Enable User-ID feature in GA4 dashboard

