"""Unit tests for update email service."""

from datetime import UTC, datetime
from pathlib import Path
from tempfile import NamedTemporaryFile
from unittest.mock import Mock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.models import Base, User, UserNotificationChannel
from app.models.dto import EmailSendResult, UpdateEmailConfig
from app.services.email_service import EmailService
from app.services.update_email_service import UpdateEmailService


@pytest.fixture
def test_db_engine():
    """Create a test database engine."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    return engine


@pytest.fixture
def test_session(test_db_engine):
    """Create a test database session."""
    TestingSessionLocal = sessionmaker(
        autocommit=False, autoflush=False, bind=test_db_engine
    )
    session = TestingSessionLocal()
    yield session
    session.rollback()
    session.close()


@pytest.fixture
def mock_email_service():
    """Create a mock email service."""
    service = Mock(spec=EmailService)
    service.send_email.return_value = EmailSendResult(
        success=True, message_id="test-msg-123", error=None, provider="ses"
    )
    service.send_raw_email.return_value = EmailSendResult(
        success=True, message_id="test-msg-123", error=None, provider="ses"
    )
    return service


@pytest.fixture
def test_users(test_session):
    """Create test users with notification channels."""
    users_data = [
        {
            "email": "active@example.com",
            "is_active": True,
            "is_deleted": False,
            "has_verified_email": True,
            "email_bounced": False,
        },
        {
            "email": "inactive@example.com",
            "is_active": False,
            "is_deleted": False,
            "has_verified_email": True,
            "email_bounced": False,
        },
        {
            "email": "deleted@example.com",
            "is_active": True,
            "is_deleted": True,
            "has_verified_email": True,
            "email_bounced": False,
        },
        {
            "email": "bounced@example.com",
            "is_active": True,
            "is_deleted": False,
            "has_verified_email": True,
            "email_bounced": True,
        },
        {
            "email": "unverified@example.com",
            "is_active": True,
            "is_deleted": False,
            "has_verified_email": False,
            "email_bounced": False,
        },
        {
            "email": "eligible2@example.com",
            "is_active": True,
            "is_deleted": False,
            "has_verified_email": True,
            "email_bounced": False,
        },
    ]

    users = []
    for user_data in users_data:
        user = User(
            email=user_data["email"],
            auth_provider="google",
            auth_provider_id=f"google_{user_data['email']}",
            is_active=user_data["is_active"],
            is_deleted=user_data["is_deleted"],
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        test_session.add(user)
        test_session.flush()

        if user_data["has_verified_email"]:
            channel = UserNotificationChannel(
                user_id=user.id,
                channel_type="email",
                channel_value=user_data["email"],
                is_enabled=True,
                is_verified=user_data["has_verified_email"],
                email_bounced=user_data["email_bounced"],
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
            test_session.add(channel)

        users.append(user)

    test_session.commit()
    return users


class TestUpdateEmailService:
    """Test cases for UpdateEmailService."""

    def test_get_eligible_users_returns_only_active_verified(
        self, test_session, mock_email_service, test_users
    ):
        """Test that get_eligible_users returns only active, verified users."""
        service = UpdateEmailService(
            session=test_session, email_service=mock_email_service
        )

        eligible = service.get_eligible_users()

        # Should only return active@example.com and eligible2@example.com
        assert len(eligible) == 2
        emails = {user.email for user in eligible}
        assert "active@example.com" in emails
        assert "eligible2@example.com" in emails
        assert "inactive@example.com" not in emails
        assert "deleted@example.com" not in emails
        assert "bounced@example.com" not in emails
        assert "unverified@example.com" not in emails

    def test_get_eligible_users_excludes_bounced(
        self, test_session, mock_email_service, test_users
    ):
        """Test that bounced emails are excluded."""
        service = UpdateEmailService(
            session=test_session, email_service=mock_email_service
        )

        eligible = service.get_eligible_users()

        emails = {user.email for user in eligible}
        assert "bounced@example.com" not in emails

    def test_send_update_email_test_mode_sends_to_test_user(
        self, test_session, mock_email_service
    ):
        """Test that test_mode sends only to test user."""
        with patch("app.services.update_email_service.settings") as mock_settings:
            mock_settings.test_email_recipient = "test@example.com"

            config = UpdateEmailConfig(
                subject="Test Subject",
                body_html="<p>Test body</p>",
                test_mode=True,
            )

            service = UpdateEmailService(
                session=test_session, email_service=mock_email_service
            )

            summary = service.send_update_email(config)

            assert summary.total_recipients == 1
            assert summary.successful == 1
            assert summary.failed == 0

            # Verify email was sent to test user
            mock_email_service.send_email.assert_called_once()
            call_args = mock_email_service.send_email.call_args
            assert call_args[1]["to_email"] == "test@example.com"
            assert call_args[1]["subject"] == "Test Subject"
            # HTML body is wrapped in template, but should contain original content
            html_body = call_args[1]["html_body"]
            assert "<p>Test body</p>" in html_body
            assert "<!DOCTYPE html>" in html_body  # Template wrapper

    def test_send_update_email_production_mode_sends_to_all_eligible(
        self, test_session, mock_email_service, test_users
    ):
        """Test that production mode sends to all eligible users."""
        config = UpdateEmailConfig(
            subject="Test Subject",
            body_html="<p>Test body</p>",
            test_mode=False,
            batch_size=10,  # Large batch to send all at once
        )

        service = UpdateEmailService(
            session=test_session, email_service=mock_email_service
        )

        summary = service.send_update_email(config)

        # Should send to 2 eligible users
        assert summary.total_recipients == 2
        assert summary.successful == 2
        assert summary.failed == 0

        # Verify emails were sent
        assert mock_email_service.send_email.call_count == 2

    def test_send_update_email_batch_processing(
        self, test_session, mock_email_service, test_users
    ):
        """Test that batch processing respects batch_size and delay."""
        import time

        config = UpdateEmailConfig(
            subject="Test Subject",
            body_html="<p>Test body</p>",
            test_mode=False,
            batch_size=1,  # Small batch size
            batch_delay_seconds=0.1,  # Short delay for testing
        )

        service = UpdateEmailService(
            session=test_session, email_service=mock_email_service
        )

        start_time = time.time()
        summary = service.send_update_email(config)
        elapsed = time.time() - start_time

        # Should send to 2 eligible users in 2 batches
        assert summary.total_recipients == 2
        assert summary.successful == 2

        # Should have some delay (at least 0.1 seconds between batches)
        # Allow some tolerance for test execution time
        assert elapsed >= 0.05  # At least some delay occurred

    def test_send_update_email_continues_on_individual_failures(
        self, test_session, mock_email_service, test_users
    ):
        """Test that individual failures don't stop the process."""
        # Make second call fail
        mock_email_service.send_email.side_effect = [
            EmailSendResult(
                success=True, message_id="msg1", error=None, provider="ses"
            ),
            EmailSendResult(
                success=False, message_id=None, error="Rate limit", provider="ses"
            ),
        ]

        config = UpdateEmailConfig(
            subject="Test Subject",
            body_html="<p>Test body</p>",
            test_mode=False,
            batch_size=10,
        )

        service = UpdateEmailService(
            session=test_session, email_service=mock_email_service
        )

        summary = service.send_update_email(config)

        # Should attempt to send to both users
        assert summary.total_recipients == 2
        assert summary.successful == 1
        assert summary.failed == 1

    def test_send_update_email_no_eligible_users(
        self, test_session, mock_email_service
    ):
        """Test behavior when no eligible users exist."""
        config = UpdateEmailConfig(
            subject="Test Subject",
            body_html="<p>Test body</p>",
            test_mode=False,
        )

        service = UpdateEmailService(
            session=test_session, email_service=mock_email_service
        )

        summary = service.send_update_email(config)

        assert summary.total_recipients == 0
        assert summary.successful == 0
        assert summary.failed == 0

        # Should not attempt to send any emails
        mock_email_service.send_email.assert_not_called()

    def test_send_update_email_exception_handling(
        self, test_session, mock_email_service, test_users
    ):
        """Test that exceptions are caught and reported."""
        # Make email service raise exception
        mock_email_service.send_email.side_effect = Exception("Network error")

        config = UpdateEmailConfig(
            subject="Test Subject",
            body_html="<p>Test body</p>",
            test_mode=False,
            batch_size=10,
        )

        service = UpdateEmailService(
            session=test_session, email_service=mock_email_service
        )

        summary = service.send_update_email(config)

        # Should report failures but continue
        assert summary.total_recipients == 2
        assert summary.successful == 0
        assert summary.failed == 2

    def test_send_update_email_test_mode_no_test_email_configured(
        self, test_session, mock_email_service
    ):
        """Test that missing test email raises error."""
        with patch("app.services.update_email_service.settings") as mock_settings:
            mock_settings.test_email_recipient = None

            config = UpdateEmailConfig(
                subject="Test Subject",
                body_html="<p>Test body</p>",
                test_mode=True,
            )

            service = UpdateEmailService(
                session=test_session, email_service=mock_email_service
            )

            with pytest.raises(ValueError, match="TEST_EMAIL_RECIPIENT not configured"):
                service.send_update_email(config)


class TestUpdateEmailServiceScreenshots:
    """Test cases for screenshot handling in UpdateEmailService."""

    @pytest.fixture
    def temp_image_file(self):
        """Create a temporary image file for testing."""
        # Create a simple PNG file (minimal valid PNG)
        png_data = (
            b"\x89PNG\r\n\x1a\n"
            b"\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00"
            b"\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01"
            b"\r\n-\xdb\x00\x00\x00\x00IEND\xaeB`\x82"
        )

        with NamedTemporaryFile(delete=False, suffix=".png") as f:
            f.write(png_data)
            temp_path = f.name

        yield temp_path

        # Cleanup
        try:
            Path(temp_path).unlink()
        except Exception:
            pass

    def test_screenshot_validation_file_exists(
        self, test_session, mock_email_service, temp_image_file
    ):
        """Test that screenshot validation checks file exists."""
        config = UpdateEmailConfig(
            subject="Test",
            body_html="<p>Test</p>",
            test_mode=True,
            screenshots=[temp_image_file],
        )

        service = UpdateEmailService(
            session=test_session, email_service=mock_email_service
        )

        with patch("app.services.update_email_service.settings") as mock_settings:
            mock_settings.test_email_recipient = "test@example.com"
            summary = service.send_update_email(config)

            # Should succeed
            assert summary.successful == 1
            # Should use send_raw_email for screenshots
            mock_email_service.send_raw_email.assert_called_once()

    def test_screenshot_validation_missing_file(self):
        """Test that missing screenshot file fails validation."""
        with pytest.raises(ValueError, match="Screenshot file not found"):
            UpdateEmailConfig(
                subject="Test",
                body_html="<p>Test</p>",
                test_mode=True,
                screenshots=["/nonexistent/file.png"],
            )

    def test_screenshot_validation_invalid_format(self, temp_image_file):
        """Test that invalid image format fails validation."""
        # Create a text file with .png extension
        invalid_file = temp_image_file.replace(".png", ".txt")
        Path(invalid_file).write_text("not an image")

        try:
            with pytest.raises(ValueError, match="must be PNG, JPG, or GIF"):
                UpdateEmailConfig(
                    subject="Test",
                    body_html="<p>Test</p>",
                    test_mode=True,
                    screenshots=[invalid_file],
                )
        finally:
            Path(invalid_file).unlink()

    def test_screenshot_validation_max_limit(self, temp_image_file):
        """Test that max 10 screenshots limit is enforced."""
        screenshots = [temp_image_file] * 11

        with pytest.raises(ValueError, match="Maximum 10 screenshots allowed"):
            UpdateEmailConfig(
                subject="Test",
                body_html="<p>Test</p>",
                test_mode=True,
                screenshots=screenshots,
            )

    def test_screenshot_embedding_in_email(
        self, test_session, mock_email_service, temp_image_file
    ):
        """Test that screenshots are embedded in email."""
        config = UpdateEmailConfig(
            subject="Test",
            body_html='<p>Test <img src="test.png"></p>',
            test_mode=True,
            screenshots=[temp_image_file],
        )

        service = UpdateEmailService(
            session=test_session, email_service=mock_email_service
        )

        with patch("app.services.update_email_service.settings") as mock_settings:
            mock_settings.test_email_recipient = "test@example.com"
            mock_settings.email_from_address = "noreply@example.com"
            mock_settings.email_from_name = "Test"

            summary = service.send_update_email(config)

            assert summary.successful == 1
            # Verify send_raw_email was called (for multipart email with images)
            mock_email_service.send_raw_email.assert_called_once()

            # Verify the raw message contains image data
            call_args = mock_email_service.send_raw_email.call_args
            raw_message = call_args[1]["raw_message"]
            assert b"image/png" in raw_message
            assert b"Content-ID" in raw_message


class TestUpdateEmailServiceAutoGeneration:
    """Test cases for auto-generation feature."""

    def test_generate_content_from_features_with_recent_features(
        self, test_session, mock_email_service, tmp_path
    ):
        """Test generating content from recent features."""
        # Create a mock specs directory with a recent spec file
        specs_dir = tmp_path / "specs" / "001-test-feature"
        specs_dir.mkdir(parents=True)
        spec_file = specs_dir / "spec.md"
        spec_file.write_text(
            "# Feature Specification: Test Feature\n\n## Summary\n\nThis is a test feature."
        )

        service = UpdateEmailService(
            session=test_session, email_service=mock_email_service
        )

        config = service.generate_content_from_features(
            days_back=30, specs_dir=str(tmp_path / "specs")
        )

        assert isinstance(config, UpdateEmailConfig)
        assert config.subject is not None
        assert config.body_html is not None
        assert (
            "Test Feature" in config.body_html
            or "test feature" in config.subject.lower()
        )
        assert config.test_mode is True  # Default to test mode

    def test_generate_content_from_features_no_features(
        self, test_session, mock_email_service, tmp_path
    ):
        """Test generating content when no features found."""
        # Create empty specs directory
        specs_dir = tmp_path / "specs"
        specs_dir.mkdir()

        service = UpdateEmailService(
            session=test_session, email_service=mock_email_service
        )

        config = service.generate_content_from_features(
            days_back=1, specs_dir=str(specs_dir)  # Very short time window
        )

        assert isinstance(config, UpdateEmailConfig)
        assert config.subject == "Recent Updates"
        assert "No recent features found" in config.body_html
        assert config.test_mode is True

    def test_generate_content_from_features_respects_time_range(
        self, test_session, mock_email_service, tmp_path
    ):
        """Test that time range parameter is respected."""
        # Create an old spec file (modify time in the past)
        specs_dir = tmp_path / "specs" / "001-old-feature"
        specs_dir.mkdir(parents=True)
        spec_file = specs_dir / "spec.md"
        spec_file.write_text(
            "# Feature Specification: Old Feature\n\n## Summary\n\nOld."
        )

        # Set modification time to 60 days ago
        import time

        old_time = time.time() - (60 * 24 * 60 * 60)
        spec_file.touch()
        import os

        os.utime(spec_file, (old_time, old_time))

        service = UpdateEmailService(
            session=test_session, email_service=mock_email_service
        )

        # Look back only 30 days
        config = service.generate_content_from_features(
            days_back=30, specs_dir=str(tmp_path / "specs")
        )

        # Should not include the old feature
        assert "Old Feature" not in config.body_html
        assert "No recent features found" in config.body_html

    def test_generate_content_from_features_invalid_specs_dir(
        self, test_session, mock_email_service
    ):
        """Test that invalid specs directory raises error."""
        service = UpdateEmailService(
            session=test_session, email_service=mock_email_service
        )

        with pytest.raises(ValueError, match="Specs directory not found"):
            service.generate_content_from_features(
                days_back=30, specs_dir="/nonexistent/path"
            )
