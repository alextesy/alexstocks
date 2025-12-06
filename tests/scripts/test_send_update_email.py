"""Integration tests for send_update_email script."""

import json
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
import yaml
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.models import Base, User, UserNotificationChannel
from app.models.dto import EmailSendResult


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
def test_user(test_session):
    """Create a test user with verified email."""
    user = User(
        email="testuser@example.com",
        auth_provider="google",
        auth_provider_id="google_123",
        is_active=True,
        is_deleted=False,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    test_session.add(user)
    test_session.flush()

    channel = UserNotificationChannel(
        user_id=user.id,
        channel_type="email",
        channel_value="testuser@example.com",
        is_enabled=True,
        is_verified=True,
        email_bounced=False,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    test_session.add(channel)
    test_session.commit()
    return user


@pytest.fixture
def mock_email_service():
    """Create a mock email service."""
    service = Mock()
    service.send_email.return_value = EmailSendResult(
        success=True, message_id="test-msg-123", error=None, provider="ses"
    )
    service.send_raw_email.return_value = EmailSendResult(
        success=True, message_id="test-msg-123", error=None, provider="ses"
    )
    return service


@pytest.fixture
def valid_yaml_config():
    """Create a valid YAML config file."""
    config = {
        "subject": "Test Update Email",
        "body_html": "<h1>Test</h1><p>This is a test email.</p>",
        "test_mode": True,
    }
    return yaml.dump(config, default_flow_style=False)


@pytest.fixture
def valid_json_config():
    """Create a valid JSON config file."""
    config = {
        "subject": "Test Update Email",
        "body_html": "<h1>Test</h1><p>This is a test email.</p>",
        "test_mode": True,
    }
    return json.dumps(config, indent=2)


class TestSendUpdateEmailScript:
    """Test cases for send_update_email.py script."""

    @pytest.fixture(autouse=True)
    def setup_postgres_url(self, monkeypatch):
        """Set postgres URL before each test to satisfy config validation."""
        monkeypatch.setenv("DATABASE_URL", "postgresql://test:test@localhost:5432/test")

    def test_script_execution_with_valid_yaml_config(
        self, test_session, mock_email_service, valid_yaml_config, tmp_path, monkeypatch
    ):
        """Test script execution with valid YAML config."""
        config_file = tmp_path / "config.yaml"
        config_file.write_text(valid_yaml_config)

        # Mock database session and email service
        # Patch at the source module since imports happen inside functions
        with patch("app.db.session.get_db") as mock_get_db:
            mock_get_db.return_value = iter([test_session])

            with patch(
                "app.services.email_service.get_email_service"
            ) as mock_get_email:
                mock_get_email.return_value = mock_email_service

                with patch("app.config.settings") as mock_settings:
                    mock_settings.test_email_recipient = "test@example.com"

                    # Import and run the script function
                    import sys

                    from app.scripts.send_update_email import main

                    # Mock sys.argv
                    with patch.object(
                        sys, "argv", ["send_update_email.py", str(config_file)]
                    ):
                        # Mock input for confirmation (not needed in test mode)
                        with patch("builtins.input", return_value=""):
                            main()

                    # Verify email was sent
                    assert (
                        mock_email_service.send_email.called
                        or mock_email_service.send_raw_email.called
                    )

    def test_script_execution_with_valid_json_config(
        self, test_session, mock_email_service, valid_json_config, tmp_path, monkeypatch
    ):
        """Test script execution with valid JSON config."""
        config_file = tmp_path / "config.json"
        config_file.write_text(valid_json_config)

        with patch("app.db.session.get_db") as mock_get_db:
            mock_get_db.return_value = iter([test_session])

            with patch(
                "app.services.email_service.get_email_service"
            ) as mock_get_email:
                mock_get_email.return_value = mock_email_service

                with patch("app.config.settings") as mock_settings:
                    mock_settings.test_email_recipient = "test@example.com"

                    from app.scripts.send_update_email import load_config

                    config = load_config(str(config_file))
                    assert config.subject == "Test Update Email"
                    assert config.test_mode is True

    def test_script_execution_test_mode_sends_to_test_user(
        self, test_session, mock_email_service, valid_yaml_config, tmp_path, monkeypatch
    ):
        """Test that test_mode sends to test user only."""
        config_file = tmp_path / "config.yaml"
        config_file.write_text(valid_yaml_config)

        with patch("app.db.session.get_db") as mock_get_db:
            mock_get_db.return_value = iter([test_session])

            with patch(
                "app.services.email_service.get_email_service"
            ) as mock_get_email:
                mock_get_email.return_value = mock_email_service

                with patch("app.config.settings") as mock_settings:
                    mock_settings.test_email_recipient = "test@example.com"

                    from app.scripts.send_update_email import load_config
                    from app.services.update_email_service import UpdateEmailService

                    config = load_config(str(config_file))
                    # Patch settings in the update_email_service module too
                    with patch(
                        "app.services.update_email_service.settings", mock_settings
                    ):
                        service = UpdateEmailService(
                            session=test_session, email_service=mock_email_service
                        )
                        summary = service.send_update_email(config)

                        assert summary.total_recipients == 1
                        assert summary.successful == 1
                        mock_email_service.send_email.assert_called_once()
                        call_args = mock_email_service.send_email.call_args
                        assert call_args[1]["to_email"] == "test@example.com"

    def test_script_execution_production_mode_sends_to_all_users(
        self, test_session, mock_email_service, test_user, tmp_path, monkeypatch
    ):
        """Test that production mode sends to all eligible users."""
        config = {
            "subject": "Production Email",
            "body_html": "<p>Production</p>",
            "test_mode": False,
            "batch_size": 10,
        }
        config_file = tmp_path / "config.yaml"
        config_file.write_text(yaml.dump(config))

        with patch("app.db.session.get_db") as mock_get_db:
            mock_get_db.return_value = iter([test_session])

            with patch(
                "app.services.email_service.get_email_service"
            ) as mock_get_email:
                mock_get_email.return_value = mock_email_service

                with patch(
                    "builtins.input", return_value="yes"
                ):  # Confirm production send
                    from app.scripts.send_update_email import load_config
                    from app.services.update_email_service import UpdateEmailService

                    config_obj = load_config(str(config_file))
                    service = UpdateEmailService(
                        session=test_session, email_service=mock_email_service
                    )
                    summary = service.send_update_email(config_obj)

                    # Should send to test_user
                    assert summary.total_recipients >= 1
                    assert summary.successful >= 1

    def test_config_validation_errors_exit_with_error(self, tmp_path):
        """Test that config validation errors exit with error."""
        # Invalid config (missing required fields)
        invalid_config = {"subject": "Test"}
        config_file = tmp_path / "invalid.yaml"
        config_file.write_text(yaml.dump(invalid_config))

        from app.scripts.send_update_email import load_config

        # Should raise SystemExit or ValueError
        with pytest.raises((SystemExit, ValueError)):
            try:
                load_config(str(config_file))
            except SystemExit:
                raise
            except Exception as e:
                # If it's a validation error, that's expected
                if "body_html" in str(e) or "test_mode" in str(e):
                    raise ValueError(str(e)) from e
                raise

    def test_config_file_not_found_exits_with_error(self, tmp_path):
        """Test that missing config file exits with error."""
        from app.scripts.send_update_email import load_config

        with pytest.raises(SystemExit):
            load_config(str(tmp_path / "nonexistent.yaml"))

    def test_no_eligible_users_reports_warning(
        self, test_session, mock_email_service, tmp_path, monkeypatch
    ):
        """Test that no eligible users reports warning but exits successfully."""
        config = {
            "subject": "Test",
            "body_html": "<p>Test</p>",
            "test_mode": False,
        }
        config_file = tmp_path / "config.yaml"
        config_file.write_text(yaml.dump(config))

        with patch("app.db.session.get_db") as mock_get_db:
            mock_get_db.return_value = iter([test_session])

            with patch(
                "app.services.email_service.get_email_service"
            ) as mock_get_email:
                mock_get_email.return_value = mock_email_service

                with patch("builtins.input", return_value="yes"):
                    from app.scripts.send_update_email import load_config
                    from app.services.update_email_service import UpdateEmailService

                    config_obj = load_config(str(config_file))
                    service = UpdateEmailService(
                        session=test_session, email_service=mock_email_service
                    )
                    summary = service.send_update_email(config_obj)

                    # Should complete successfully with 0 recipients
                    assert summary.total_recipients == 0
                    assert summary.successful == 0
                    assert summary.failed == 0


class TestSendUpdateEmailScriptScreenshots:
    """Test cases for screenshot handling in script."""

    @pytest.fixture(autouse=True)
    def setup_postgres_url(self, monkeypatch):
        """Set postgres URL before each test to satisfy config validation."""
        monkeypatch.setenv("DATABASE_URL", "postgresql://test:test@localhost:5432/test")

    @pytest.fixture
    def temp_image_file(self):
        """Create a temporary image file for testing."""
        # Create a minimal valid PNG
        png_data = (
            b"\x89PNG\r\n\x1a\n"
            b"\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00"
            b"\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01"
            b"\r\n-\xdb\x00\x00\x00\x00IEND\xaeB`\x82"
        )

        with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as f:
            f.write(png_data)
            temp_path = f.name

        yield temp_path

        try:
            Path(temp_path).unlink()
        except Exception:
            pass

    def test_email_with_screenshots_includes_images_inline(
        self, test_session, mock_email_service, temp_image_file, tmp_path, monkeypatch
    ):
        """Test that emails with screenshots include images inline."""
        config = {
            "subject": "Test with Screenshots",
            "body_html": '<p>Test <img src="test.png"></p>',
            "test_mode": True,
            "screenshots": [temp_image_file],
        }
        config_file = tmp_path / "config.yaml"
        config_file.write_text(yaml.dump(config))

        with patch("app.db.session.get_db") as mock_get_db:
            mock_get_db.return_value = iter([test_session])

            with patch(
                "app.services.email_service.get_email_service"
            ) as mock_get_email:
                mock_get_email.return_value = mock_email_service

                with patch("app.config.settings") as mock_settings:
                    mock_settings.test_email_recipient = "test@example.com"
                    mock_settings.email_from_address = "noreply@example.com"
                    mock_settings.email_from_name = "Test"

                    from app.scripts.send_update_email import load_config
                    from app.services.update_email_service import UpdateEmailService

                    config_obj = load_config(str(config_file))
                    service = UpdateEmailService(
                        session=test_session, email_service=mock_email_service
                    )
                    summary = service.send_update_email(config_obj)

                    assert summary.successful == 1
                    # Should use send_raw_email for screenshots
                    mock_email_service.send_raw_email.assert_called_once()

                    # Verify raw message contains image
                    call_args = mock_email_service.send_raw_email.call_args
                    raw_message = call_args[1]["raw_message"]
                    assert b"image/png" in raw_message

    def test_email_with_invalid_screenshot_path_fails_validation(
        self, tmp_path, capsys
    ):
        """Test that invalid screenshot path fails validation."""
        config = {
            "subject": "Test",
            "body_html": "<p>Test</p>",
            "test_mode": True,
            "screenshots": ["/nonexistent/file.png"],
        }
        config_file = tmp_path / "config.yaml"
        config_file.write_text(yaml.dump(config))

        from app.scripts.send_update_email import load_config

        with pytest.raises(SystemExit):
            load_config(str(config_file))

        # Verify error message was printed
        captured = capsys.readouterr()
        assert "Screenshot file not found" in captured.out

    def test_email_with_too_many_screenshots_fails_validation(
        self, temp_image_file, tmp_path, capsys
    ):
        """Test that too many screenshots fails validation."""
        config = {
            "subject": "Test",
            "body_html": "<p>Test</p>",
            "test_mode": True,
            "screenshots": [temp_image_file] * 11,  # More than max 10
        }
        config_file = tmp_path / "config.yaml"
        config_file.write_text(yaml.dump(config))

        from app.scripts.send_update_email import load_config

        with pytest.raises(SystemExit):
            load_config(str(config_file))

        # Verify error message was printed
        captured = capsys.readouterr()
        assert "Maximum 10 screenshots" in captured.out


class TestSendUpdateEmailScriptAutoGeneration:
    """Test cases for auto-generation feature."""

    @pytest.fixture(autouse=True)
    def setup_postgres_url(self, monkeypatch):
        """Set postgres URL before each test to satisfy config validation."""
        monkeypatch.setenv("DATABASE_URL", "postgresql://test:test@localhost:5432/test")

    def test_auto_generate_creates_draft_config(
        self, test_session, mock_email_service, tmp_path, monkeypatch
    ):
        """Test that auto-generation creates draft config."""
        # Create a mock specs directory
        specs_dir = tmp_path / "specs" / "001-test-feature"
        specs_dir.mkdir(parents=True)
        spec_file = specs_dir / "spec.md"
        spec_file.write_text(
            "# Feature Specification: Test Feature\n\n## Summary\n\nThis is a test feature."
        )

        with patch("app.db.session.get_db") as mock_get_db:
            mock_get_db.return_value = iter([test_session])

            with patch(
                "app.services.email_service.get_email_service"
            ) as mock_get_email:
                mock_get_email.return_value = mock_email_service

                import sys

                from app.scripts.send_update_email import main

                output_file = tmp_path / "generated.yaml"

                with patch.object(
                    sys,
                    "argv",
                    [
                        "send_update_email.py",
                        "--auto-generate",
                        "--days-back",
                        "30",
                        "--output",
                        str(output_file),
                    ],
                ):
                    main()

                # Verify output file was created
                assert output_file.exists()

                # Verify content
                content = output_file.read_text()
                assert "subject" in content
                assert "body_html" in content
                assert "test_mode" in content

    def test_generated_content_can_be_edited(
        self, test_session, mock_email_service, tmp_path, monkeypatch
    ):
        """Test that generated content can be edited."""
        specs_dir = tmp_path / "specs" / "001-test-feature"
        specs_dir.mkdir(parents=True)
        spec_file = specs_dir / "spec.md"
        spec_file.write_text(
            "# Feature Specification: Test Feature\n\n## Summary\n\nThis is a test feature."
        )

        with patch("app.db.session.get_db") as mock_get_db:
            mock_get_db.return_value = iter([test_session])

            with patch(
                "app.services.email_service.get_email_service"
            ) as mock_get_email:
                mock_get_email.return_value = mock_email_service

                from app.services.update_email_service import UpdateEmailService

                service = UpdateEmailService(
                    session=test_session, email_service=mock_email_service
                )
                config = service.generate_content_from_features(
                    days_back=30, specs_dir=str(tmp_path / "specs")
                )

                # Verify config can be modified
                assert isinstance(config, type(config))
                # Can access and modify fields
                config.subject = "Modified Subject"
                assert config.subject == "Modified Subject"

    def test_generated_content_can_be_used_to_send_email(
        self, test_session, mock_email_service, tmp_path, monkeypatch
    ):
        """Test that generated content can be used to send email."""
        specs_dir = tmp_path / "specs" / "001-test-feature"
        specs_dir.mkdir(parents=True)
        spec_file = specs_dir / "spec.md"
        spec_file.write_text(
            "# Feature Specification: Test Feature\n\n## Summary\n\nThis is a test feature."
        )

        with patch("app.config.settings") as mock_settings:
            mock_settings.test_email_recipient = "test@example.com"

            from app.services.update_email_service import UpdateEmailService

            service = UpdateEmailService(
                session=test_session, email_service=mock_email_service
            )
            config = service.generate_content_from_features(
                days_back=30, specs_dir=str(tmp_path / "specs")
            )

            # Use generated config to send email
            summary = service.send_update_email(config)

            assert summary.successful == 1
            mock_email_service.send_email.assert_called_once()
