#!/usr/bin/env python3
"""Send a test email using the email service."""

import sys
from datetime import datetime

from app.config import settings
from app.services.email_service import get_email_service


def send_test_email():
    """Send a test email to verify email service configuration."""
    print("🔧 Checking AWS credentials...")
    try:
        import boto3

        sts = boto3.client("sts")
        sts.get_caller_identity()
        print("✅ AWS credentials verified")
    except Exception as e:
        print("❌ AWS credentials not found!")
        print("   Please set up AWS credentials:")
        print("   export AWS_ACCESS_KEY_ID=your-key")
        print("   export AWS_SECRET_ACCESS_KEY=your-secret")
        print("   export AWS_DEFAULT_REGION=us-east-1")
        print(f"   Error: {e}")
        return

    try:
        # Get the email service
        service = get_email_service()

        # Create test email content
        subject = f"AlexStocks Email Service Test - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"

        html_body = f"""
        <html>
        <body>
            <h2>🎉 AlexStocks Email Service Test</h2>
            <p>This is a test email to verify that your email service is working correctly.</p>

            <h3>Configuration Details:</h3>
            <ul>
                <li><strong>Provider:</strong> {settings.email_provider}</li>
                <li><strong>From:</strong> {settings.email_from_name} &lt;{settings.email_from_address}&gt;</li>
                <li><strong>To:</strong> {settings.test_email_recipient}</li>
                <li><strong>Region:</strong> {settings.aws_ses_region}</li>
            </ul>

            <h3>Timestamp:</h3>
            <p>Sent at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}</p>

            <p>If you're reading this, your email service is working! 🚀</p>

            <hr>
            <p><em>This is an automated test email from AlexStocks Market Pulse.</em></p>
        </body>
        </html>
        """

        text_body = f"""
        AlexStocks Email Service Test
        ==============================

        This is a test email to verify that your email service is working correctly.

        Configuration Details:
        - Provider: {settings.email_provider}
        - From: {settings.email_from_name} <{settings.email_from_address}>
        - To: {settings.test_email_recipient}
        - Region: {settings.aws_ses_region}

        Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}

        If you're reading this, your email service is working! 🚀

        ---
        This is an automated test email from AlexStocks Market Pulse.
        """

        # Send the email
        print(f"📧 Sending test email to {settings.test_email_recipient}...")
        result = service.send_email(
            to_email=settings.test_email_recipient,
            subject=subject,
            html_body=html_body,
            text_body=text_body,
        )

        if result.success:
            print("✅ Test email sent successfully!")
            print(f"   Message ID: {result.message_id}")
            print(f"   Provider: {result.provider}")
        else:
            print("❌ Failed to send test email!")
            print(f"   Error: {result.error}")
            sys.exit(1)

    except Exception as e:
        print(f"❌ Error sending test email: {e}")
        sys.exit(1)


if __name__ == "__main__":
    send_test_email()
