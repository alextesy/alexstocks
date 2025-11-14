# Email Service Setup Guide

## Required Environment Variables

Add these to your `.env` file:

```bash
# Email Service Configuration
EMAIL_PROVIDER=ses
EMAIL_FROM_ADDRESS=noreply@alexstocks.com
EMAIL_FROM_NAME=AlexStocks
AWS_SES_REGION=us-east-1

# Test Email Configuration (Optional - defaults to test@example.com for development)
TEST_EMAIL_RECIPIENT=your-verified-email@example.com
```

ℹ️ **Note**: `TEST_EMAIL_RECIPIENT` defaults to `test@example.com` for development/testing. Set it in your `.env` file for production use with a verified email address.

## Prerequisites

### AWS Credentials Setup
Before testing emails, you need AWS credentials with SES permissions:

```bash
# Option 1: Environment variables
export AWS_ACCESS_KEY_ID=your-access-key
export AWS_SECRET_ACCESS_KEY=your-secret-key
export AWS_DEFAULT_REGION=us-east-1

# Option 2: AWS CLI configuration
aws configure

# Verify credentials work
aws sts get-caller-identity
```

**Note**: For EC2/production, IAM roles are used automatically - no credentials needed in `.env`.

## AWS SES Setup Steps

### 1. Domain Verification
✅ **Completed**: You verified `alexstocks.com` domain in AWS SES

### 2. Email Address Verification
You need to verify the email address you'll use for testing:

**Option A: Verify your personal email**
```bash
# In AWS SES Console:
# 1. Go to "Verified identities"
# 2. Click "Create identity" > "Email address"
# 3. Enter: your-email@example.com
# 4. AWS will send verification email
# 5. Click verification link
```

**Option B: Use an alexstocks.com email**
- Set up email forwarding in GoDaddy: `test@alexstocks.com` → `your-email@example.com`
- Then verify `test@alexstocks.com` in SES

### 3. Update .env File
```bash
# Replace with your verified email address
TEST_EMAIL_RECIPIENT=your-verified-email@example.com
```

### 4. Test the Service
```bash
make send-test-email
```

## Production Deployment

### Move Out of SES Sandbox
```bash
# In AWS SES Console > Account dashboard
# Click "Request production access"
# Fill out the form explaining your use case
# AWS reviews and approves (usually within hours-days)
```

### EC2 Deployment
- AWS credentials are automatically available via IAM role
- No need to set AWS_ACCESS_KEY_ID/AWS_SECRET_ACCESS_KEY in .env
- Just ensure the EC2 instance has the `AmazonSESFullAccess` policy

## Troubleshooting

### Test Email Fails
- **Error**: "Email address is not verified"
- **Solution**: Verify the TEST_EMAIL_RECIPIENT email in SES Console

### AWS Credentials Issues
- **Error**: "Unable to locate credentials"
- **Solution**: Ensure EC2 has proper IAM role with SES permissions

### Domain Not Verified
- **Error**: "Domain is not verified"
- **Solution**: Complete domain verification in SES Console (TXT record in DNS)

## Commands

```bash
# Test email service
make send-test-email

# Check email service configuration
uv run python -c "from app.config import settings; print(f'Email provider: {settings.email_provider}'); print(f'From: {settings.email_from_name} <{settings.email_from_address}>'); print(f'Test recipient: {settings.test_email_recipient}')"
```
