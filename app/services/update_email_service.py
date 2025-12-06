"""Service for sending update emails to users."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.db.models import User, UserNotificationChannel
from app.models.dto import EmailCadence, UpdateEmailConfig, UserDTO
from app.repos.user_repo import UserRepository
from app.services.email_service import EmailService

logger = logging.getLogger(__name__)


@dataclass
class UpdateEmailSummary:
    """Summary of update email send operation."""

    total_recipients: int
    successful: int
    failed: int
    elapsed_seconds: float


class UpdateEmailService:
    """Service for sending update emails to users."""

    def __init__(
        self,
        session: Session,
        email_service: EmailService,
        user_repo: UserRepository | None = None,
    ):
        """Initialize update email service.

        Args:
            session: Database session
            email_service: Email service for sending emails
            user_repo: User repository (created if not provided)
        """
        self.session = session
        self.email_service = email_service
        self.user_repo = user_repo or UserRepository(session)

    def get_eligible_users(self) -> list[UserDTO]:
        """Get all users eligible to receive update emails.

        Returns:
            List of active, non-deleted users with verified email addresses
            (excludes users with bounced emails or global email opt-outs)
        """
        stmt = (
            select(User)
            .join(
                UserNotificationChannel,
                User.id == UserNotificationChannel.user_id,
            )
            .where(
                User.is_deleted == False,  # noqa: E712
                User.is_active == True,  # noqa: E712
                UserNotificationChannel.channel_type == "email",
                UserNotificationChannel.is_enabled == True,  # noqa: E712
                UserNotificationChannel.is_verified == True,  # noqa: E712
                UserNotificationChannel.email_bounced == False,  # noqa: E712
            )
        )
        users = self.session.execute(stmt).unique().scalars().all()

        eligible_users: list[UserDTO] = []
        for user in users:
            cadence = self.user_repo.get_email_cadence(user.id)
            if cadence == EmailCadence.NONE:
                logger.info(
                    "update_email_skipped_opt_out",
                    extra={"user_id": user.id, "email": user.email},
                )
                continue
            eligible_users.append(UserRepository._user_to_dto(user))

        return eligible_users

    def send_update_email(self, config: UpdateEmailConfig) -> UpdateEmailSummary:
        """Send update email to eligible users or test user.

        Args:
            config: Update email configuration

        Returns:
            UpdateEmailSummary with send statistics
        """
        start_time = time.time()

        # Get recipients
        if config.test_mode:
            # Send only to test user
            test_email = settings.test_email_recipient
            if not test_email:
                raise ValueError("TEST_EMAIL_RECIPIENT not configured")
            recipients = [
                UserDTO(
                    id=0,
                    email=test_email,
                    auth_provider_id=None,
                    auth_provider=None,
                    is_active=True,
                    is_deleted=False,
                    created_at=datetime.now(UTC),
                    updated_at=datetime.now(UTC),
                    deleted_at=None,
                )
            ]
            logger.info(
                "update_email_test_mode",
                extra={
                    "test_email": test_email,
                    "subject": config.subject,
                },
            )
        else:
            recipients = self.get_eligible_users()
            logger.info(
                "update_email_production_mode",
                extra={
                    "recipient_count": len(recipients),
                    "subject": config.subject,
                },
            )

        if not recipients:
            logger.warning("update_email_no_recipients")
            return UpdateEmailSummary(
                total_recipients=0,
                successful=0,
                failed=0,
                elapsed_seconds=time.time() - start_time,
            )

        # Send emails in batches
        successful = 0
        failed = 0
        total = len(recipients)
        batch_size = config.batch_size
        batch_delay = config.batch_delay_seconds

        for batch_start in range(0, total, batch_size):
            batch_end = min(batch_start + batch_size, total)
            batch = recipients[batch_start:batch_end]
            batch_num = (batch_start // batch_size) + 1
            total_batches = (total + batch_size - 1) // batch_size

            logger.info(
                "update_email_batch_start",
                extra={
                    "batch_num": batch_num,
                    "total_batches": total_batches,
                    "batch_size": len(batch),
                },
            )
            # Print progress to console
            elapsed_so_far = time.time() - start_time
            remaining_batches = total_batches - batch_num
            estimated_remaining = remaining_batches * batch_delay
            print(
                f"✅ Batch {batch_num}/{total_batches}: Processing {len(batch)} emails "
                f"(Elapsed: {elapsed_so_far:.1f}s, Est. remaining: {estimated_remaining:.0f}s)"
            )

            # Wrap HTML in template for better email client compatibility
            wrapped_html = self._wrap_html_template(config.body_html)

            # Send emails in this batch
            for user in batch:
                try:
                    # Use screenshot embedding if screenshots are provided
                    if config.screenshots:
                        raw_message = self._create_email_with_screenshots(
                            to_email=user.email,
                            subject=config.subject,
                            html_body=wrapped_html,
                            screenshots=config.screenshots,
                        )
                        result = self.email_service.send_raw_email(
                            to_email=user.email,
                            raw_message=raw_message,
                        )
                    else:
                        result = self.email_service.send_email(
                            to_email=user.email,
                            subject=config.subject,
                            html_body=wrapped_html,
                            text_body=self._html_to_text(config.body_html),
                        )

                    if result.success:
                        successful += 1
                        logger.info(
                            "update_email_sent",
                            extra={
                                "user_id": user.id,
                                "email": user.email,
                                "message_id": result.message_id,
                                "timestamp": datetime.now(UTC).isoformat(),
                            },
                        )
                    else:
                        failed += 1
                        logger.error(
                            "update_email_failed",
                            extra={
                                "user_id": user.id,
                                "email": user.email,
                                "error": result.error,
                                "timestamp": datetime.now(UTC).isoformat(),
                            },
                        )
                except Exception as e:
                    failed += 1
                    logger.exception(
                        "update_email_exception",
                        extra={
                            "user_id": user.id,
                            "email": user.email,
                            "error": str(e),
                            "timestamp": datetime.now(UTC).isoformat(),
                        },
                    )

            # Wait between batches (except after the last batch)
            if batch_end < total:
                time.sleep(batch_delay)

        elapsed = time.time() - start_time
        summary = UpdateEmailSummary(
            total_recipients=total,
            successful=successful,
            failed=failed,
            elapsed_seconds=elapsed,
        )

        logger.info(
            "update_email_complete",
            extra={
                "total_recipients": summary.total_recipients,
                "successful": summary.successful,
                "failed": summary.failed,
                "elapsed_seconds": summary.elapsed_seconds,
            },
        )

        return summary

    @staticmethod
    def _wrap_html_template(html_body: str, use_template: bool = True) -> str:
        """Wrap HTML body in email-compatible template with inline CSS.

        Args:
            html_body: Raw HTML content to wrap
            use_template: Whether to wrap in template (default: True)

        Returns:
            Wrapped HTML with template or original HTML if use_template is False
        """
        if not use_template:
            return html_body

        # Email-compatible template with inline CSS and table-based layout
        # Matches the visual style of daily/weekly email templates with dark mode support
        template = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta name="color-scheme" content="light dark">
    <meta name="supported-color-schemes" content="light dark">
    <title>AlexStocks Update</title>
    <style>
        body {{
            margin: 0;
            padding: 0;
            background-color: #f4f4f7;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Arial, sans-serif;
            color: #111827;
        }}
        a {{ color: #2563eb; text-decoration: none; }}
        .email-wrapper {{
            width: 100%;
            padding: 32px 0;
        }}
        .email-container {{
            max-width: 640px;
            margin: 0 auto;
            background-color: #ffffff;
            border-radius: 16px;
            box-shadow: 0 10px 40px rgba(15, 23, 42, 0.08);
            overflow: hidden;
        }}
        .email-content {{
            padding: 32px;
        }}
        .email-footer {{
            text-align: center;
            font-size: 13px;
            color: #6b7280;
            margin-top: 24px;
            line-height: 1.5;
        }}
        .button {{
            display: inline-block;
            padding: 10px 18px;
            border-radius: 9999px;
            background-color: #111827;
            color: #ffffff !important;
            font-weight: 600;
            margin-top: 8px;
        }}
        @media (max-width: 600px) {{
            .email-content {{ padding: 20px; }}
        }}
        @media (prefers-color-scheme: dark) {{
            body {{
                background-color: #0f172a;
                color: #f1f5f9;
            }}
            a {{
                color: #93c5fd;
            }}
            .email-container {{
                background-color: #1e293b;
            }}
            .button {{
                background-color: #f8fafc;
                color: #0f172a !important;
            }}
            h1, h2, h3 {{
                color: #f1f5f9 !important;
            }}
            p {{
                color: #e2e8f0 !important;
            }}
            .email-footer, .email-footer p {{
                color: #cbd5f5 !important;
            }}
        }}
    </style>
</head>
<body>
    <div class="email-wrapper">
        <div class="email-container">
            <div class="email-content">
                {content}
            </div>
        </div>
        <div style="text-align: center; font-size: 13px; color: #6b7280; margin-top: 24px; line-height: 1.5;">
            <p style="margin: 0;">You are receiving this email because you have an active AlexStocks account.</p>
            <p style="margin: 8px 0 0 0;"><a href="https://alexstocks.com/settings" style="color: #2563eb; text-decoration: none;">Manage email preferences</a> · <a href="https://alexstocks.com" style="color: #2563eb; text-decoration: none;">Visit AlexStocks</a></p>
            <p style="font-size: 11px; font-style: italic; margin-top: 16px; color: #9ca3af;">
                <strong>Disclaimer:</strong> This is not financial advice. Always do your own research before making investment decisions.
            </p>
        </div>
    </div>
</body>
</html>"""

        return template.format(content=html_body)

    @staticmethod
    def _html_to_text(html: str) -> str:
        """Convert HTML to plain text (simple implementation).

        Args:
            html: HTML content

        Returns:
            Plain text version
        """
        # Simple HTML stripping - can be enhanced later
        import re

        # Remove script and style tags
        text = re.sub(
            r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL | re.IGNORECASE
        )
        text = re.sub(
            r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL | re.IGNORECASE
        )

        # Replace common HTML tags with newlines or spaces
        text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
        text = re.sub(r"</p>", "\n\n", text, flags=re.IGNORECASE)
        text = re.sub(r"</div>", "\n", text, flags=re.IGNORECASE)
        text = re.sub(r"</li>", "\n", text, flags=re.IGNORECASE)

        # Remove all remaining HTML tags
        text = re.sub(r"<[^>]+>", "", text)

        # Decode HTML entities (basic)
        text = text.replace("&nbsp;", " ")
        text = text.replace("&amp;", "&")
        text = text.replace("&lt;", "<")
        text = text.replace("&gt;", ">")
        text = text.replace("&quot;", '"')
        text = text.replace("&#39;", "'")

        # Clean up whitespace
        text = re.sub(r"\n\s*\n\s*\n+", "\n\n", text)
        text = text.strip()

        return text if text else "Update email - please view in HTML format."

    def _create_email_with_screenshots(
        self,
        to_email: str,
        subject: str,
        html_body: str,
        screenshots: list[str],
    ) -> bytes:
        """Create a MIME multipart email with inline screenshots.

        Args:
            to_email: Recipient email address
            subject: Email subject
            html_body: HTML email body
            screenshots: List of screenshot file paths

        Returns:
            Raw MIME message bytes

        Raises:
            ValueError: If screenshot file is invalid or too large
        """
        from_address = settings.email_from_address
        from_name = settings.email_from_name

        # Create multipart/related message for inline images
        msg = MIMEMultipart("related")
        msg["From"] = f"{from_name} <{from_address}>" if from_name else from_address
        msg["To"] = to_email
        msg["Subject"] = subject

        # Create alternative part for HTML and text
        alt = MIMEMultipart("alternative")
        msg.attach(alt)

        # Add text version
        text_body = self._html_to_text(html_body)
        alt.attach(MIMEText(text_body, "plain", "utf-8"))

        # Process screenshots and update HTML with CID references
        # Note: html_body is already wrapped in template if screenshots are used
        html_with_images = html_body
        for idx, screenshot_path in enumerate(screenshots):
            path = Path(screenshot_path)
            cid = f"image{idx + 1}"

            # Validate file size (5MB limit)
            file_size = path.stat().st_size
            max_size = 5 * 1024 * 1024  # 5MB
            if file_size > max_size:
                logger.warning(
                    "screenshot_too_large",
                    extra={
                        "path": screenshot_path,
                        "size_mb": file_size / (1024 * 1024),
                        "max_mb": 5,
                    },
                )
                # Continue but log warning

            # Read image file
            with open(path, "rb") as f:
                image_data = f.read()

            # Determine MIME type from extension
            ext = path.suffix.lower()
            mime_types = {
                ".png": "image/png",
                ".jpg": "image/jpeg",
                ".jpeg": "image/jpeg",
                ".gif": "image/gif",
            }
            mime_type = mime_types.get(ext, "image/png")

            # Create image attachment with Content-ID
            img = MIMEImage(image_data, mime_type)
            img.add_header("Content-ID", f"<{cid}>")
            img.add_header("Content-Disposition", "inline", filename=path.name)
            msg.attach(img)

            # Replace image references in HTML with CID references
            # Look for common patterns: <img src="path"> or just the filename
            import re

            # Replace any reference to the filename with CID
            filename_pattern = re.escape(path.name)
            html_with_images = re.sub(
                rf'src=["\']?([^"\'>\s]*{filename_pattern}[^"\'>\s]*)["\']?',
                f'src="cid:{cid}"',
                html_with_images,
                flags=re.IGNORECASE,
            )

        # Add HTML part
        alt.attach(MIMEText(html_with_images, "html", "utf-8"))

        # Return raw message bytes
        return msg.as_bytes()

    def generate_content_from_features(
        self,
        days_back: int = 30,
        specs_dir: str | None = None,
    ) -> UpdateEmailConfig:
        """Generate draft email content from recently implemented features.

        Args:
            days_back: Number of days to look back for features (default: 30)
            specs_dir: Directory containing spec files (default: "specs" relative to repo root)

        Returns:
            UpdateEmailConfig with generated content

        Raises:
            ValueError: If no features found or specs directory doesn't exist
        """
        from datetime import timedelta

        # Default to specs/ directory relative to repo root
        if specs_dir is None:
            # Try to find repo root (look for specs/ directory)
            current = Path.cwd()
            specs_path = current / "specs"
            # If not found, try going up one level (in case running from app/)
            if not specs_path.exists() and (current.parent / "specs").exists():
                specs_path = current.parent / "specs"
        else:
            specs_path = Path(specs_dir)

        if not specs_path.exists():
            raise ValueError(f"Specs directory not found: {specs_path}")

        # Calculate cutoff date
        cutoff_date = datetime.now(UTC) - timedelta(days=days_back)

        # Find all spec.md files
        spec_files: list[tuple[Path, datetime]] = []
        for spec_file in specs_path.rglob("spec.md"):
            # Get file modification time
            mtime = datetime.fromtimestamp(spec_file.stat().st_mtime, tz=UTC)
            if mtime >= cutoff_date:
                spec_files.append((spec_file, mtime))

        if not spec_files:
            # Return empty config if no features found
            return UpdateEmailConfig(
                subject="Recent Updates",
                body_html="<p>No recent features found.</p>",
                test_mode=True,
            )

        # Sort by modification time (newest first)
        spec_files.sort(key=lambda x: x[1], reverse=True)

        # Extract feature summaries
        features: list[dict[str, str]] = []
        for spec_file, mtime in spec_files:
            try:
                feature_info = self._extract_feature_summary(spec_file, mtime)
                if feature_info:
                    features.append(feature_info)
            except Exception as e:
                logger.warning(
                    "failed_to_extract_feature",
                    extra={"spec_file": str(spec_file), "error": str(e)},
                )

        if not features:
            return UpdateEmailConfig(
                subject="Recent Updates",
                body_html="<p>No recent features found.</p>",
                test_mode=True,
            )

        # Generate HTML content
        html_body = self._generate_feature_html(features, days_back)

        # Generate subject
        feature_count = len(features)
        if feature_count == 1:
            subject = f"New Feature: {features[0]['title']}"
        else:
            subject = f"{feature_count} New Features Available!"

        return UpdateEmailConfig(
            subject=subject,
            body_html=html_body,
            screenshots=[],
            test_mode=True,  # Default to test mode for safety
        )

    @staticmethod
    def _extract_feature_summary(
        spec_file: Path, mtime: datetime
    ) -> dict[str, str] | None:
        """Extract feature summary from spec.md file.

        Args:
            spec_file: Path to spec.md file
            mtime: File modification time

        Returns:
            Dictionary with title, summary, and date, or None if extraction fails
        """
        try:
            content = spec_file.read_text(encoding="utf-8")

            # Extract feature name from first heading
            import re

            title_match = re.search(
                r"^# Feature Specification:\s*(.+)$", content, re.MULTILINE
            )
            title = (
                title_match.group(1).strip() if title_match else spec_file.parent.name
            )

            # Extract summary from spec (look for Summary section or first paragraph)
            summary_match = re.search(
                r"## Summary\s*\n\n(.+?)(?:\n##|\Z)", content, re.DOTALL
            )
            if not summary_match:
                # Try to get first meaningful paragraph
                summary_match = re.search(
                    r"^## .+\n\n(.+?)(?:\n\n|\n##|\Z)",
                    content,
                    re.DOTALL | re.MULTILINE,
                )

            summary = (
                summary_match.group(1).strip()[:200] + "..."
                if summary_match and len(summary_match.group(1).strip()) > 200
                else (
                    summary_match.group(1).strip()
                    if summary_match
                    else "Feature implementation completed."
                )
            )

            return {
                "title": title,
                "summary": summary,
                "date": mtime.strftime("%Y-%m-%d"),
                "path": str(spec_file),
            }
        except Exception as e:
            logger.warning(
                "feature_extraction_failed",
                extra={"spec_file": str(spec_file), "error": str(e)},
            )
            return None

    @staticmethod
    def _generate_feature_html(features: list[dict[str, str]], days_back: int) -> str:
        """Generate HTML content from feature summaries.

        Args:
            features: List of feature dictionaries
            days_back: Number of days looked back

        Returns:
            HTML content string
        """
        html_parts = [
            '<div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">',
            '<h1 style="color: #333;">Recent Updates</h1>',
            f'<p style="color: #666;">Here are the features we\'ve added in the last {days_back} days:</p>',
            '<ul style="list-style: none; padding: 0;">',
        ]

        for feature in features:
            html_parts.append(
                '<li style="margin-bottom: 20px; padding: 15px; border-left: 3px solid #007bff; background-color: #f8f9fa;">'
            )
            html_parts.append(
                f'<h2 style="color: #333; margin-top: 0;">{feature["title"]}</h2>'
            )
            html_parts.append(f'<p style="color: #666;">{feature["summary"]}</p>')
            html_parts.append(
                f'<small style="color: #999;">Added: {feature["date"]}</small>'
            )
            html_parts.append("</li>")

        html_parts.extend(
            [
                "</ul>",
                '<p style="color: #666;">Try them out and let us know what you think!</p>',
                '<p><a href="https://alexstocks.com" style="color: #007bff;">Visit AlexStocks</a></p>',
                "</div>",
            ]
        )

        return "\n".join(html_parts)
