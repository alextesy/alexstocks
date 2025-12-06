#!/usr/bin/env python3
"""Send update emails to users from a config file."""

import argparse
import json
import sys
from pathlib import Path

import yaml

from app.config import settings
from app.models.dto import UpdateEmailConfig


def load_config(config_path: str) -> UpdateEmailConfig:
    """Load and validate config file.

    Args:
        config_path: Path to YAML or JSON config file

    Returns:
        Validated UpdateEmailConfig

    Raises:
        SystemExit: If config file is invalid or missing
    """
    path = Path(config_path)
    if not path.exists():
        print(f"❌ Config file not found: {config_path}")
        sys.exit(1)

    try:
        with open(path) as f:
            if path.suffix.lower() in (".yaml", ".yml"):
                data = yaml.safe_load(f)
            elif path.suffix.lower() == ".json":
                data = json.load(f)
            else:
                # Try YAML first, then JSON
                try:
                    f.seek(0)
                    data = yaml.safe_load(f)
                except Exception:
                    f.seek(0)
                    data = json.load(f)

        config = UpdateEmailConfig(**data)
        return config
    except yaml.YAMLError as e:
        print(f"❌ YAML parsing error: {e}")
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"❌ JSON parsing error: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Config validation error: {e}")
        sys.exit(1)


def format_summary(summary) -> str:
    """Format email send summary for display.

    Args:
        summary: UpdateEmailSummary object

    Returns:
        Formatted summary string
    """
    lines = [
        "",
        "📊 Summary:",
        f"   - Total recipients: {summary.total_recipients}",
        f"   - Successful: {summary.successful}",
        f"   - Failed: {summary.failed}",
        f"   - Elapsed time: {summary.elapsed_seconds:.2f} seconds",
    ]
    return "\n".join(lines)


def main():
    """Main entry point for the script."""
    parser = argparse.ArgumentParser(
        description="Send update emails to users from a config file"
    )
    parser.add_argument(
        "config_file",
        type=str,
        nargs="?",
        help="Path to YAML or JSON config file (required unless --auto-generate)",
    )
    parser.add_argument(
        "--auto-generate",
        action="store_true",
        help="Auto-generate email content from recent features",
    )
    parser.add_argument(
        "--days-back",
        type=int,
        default=30,
        help="Number of days to look back for features (default: 30)",
    )
    parser.add_argument(
        "--output",
        type=str,
        help="Output file for generated config (default: stdout)",
    )
    args = parser.parse_args()

    # Handle auto-generation
    if args.auto_generate:
        from app.db.session import get_db
        from app.services.email_service import get_email_service
        from app.services.update_email_service import UpdateEmailService

        db = next(get_db())
        email_service = get_email_service()
        update_service = UpdateEmailService(
            session=db,
            email_service=email_service,
        )

        try:
            config = update_service.generate_content_from_features(
                days_back=args.days_back
            )

            # Convert to dict for YAML output
            config_dict = {
                "subject": config.subject,
                "body_html": config.body_html,
                "screenshots": config.screenshots,
                "test_mode": config.test_mode,
                "batch_size": config.batch_size,
                "batch_delay_seconds": config.batch_delay_seconds,
            }

            import yaml

            yaml_output = yaml.dump(
                config_dict, default_flow_style=False, sort_keys=False
            )

            if args.output:
                with open(args.output, "w") as f:
                    f.write(yaml_output)
                print(f"✅ Generated config written to {args.output}")
            else:
                print("Generated config:")
                print("---")
                print(yaml_output)
                print("---")
                print("\n💡 Tip: Save this to a file and edit before sending")

        except Exception as e:
            print(f"❌ Error generating content: {e}")
            import traceback

            traceback.print_exc()
            sys.exit(1)
        finally:
            db.close()

        return

    # Require config_file if not auto-generating
    if not args.config_file:
        parser.error("config_file is required unless --auto-generate is used")

    # Load and validate config
    print("✅ Loading config file...")
    config = load_config(args.config_file)

    # Validate test mode
    if not config.test_mode:
        print("⚠️  WARNING: test_mode is False - this will send to ALL users!")
        response = input("Type 'yes' to confirm: ")
        if response.lower() != "yes":
            print("❌ Cancelled by user")
            sys.exit(1)

    # Initialize services
    print("✅ Initializing services...")
    from app.db.session import get_db
    from app.services.email_service import get_email_service
    from app.services.update_email_service import UpdateEmailService

    db = next(get_db())
    email_service = get_email_service()
    update_service = UpdateEmailService(
        session=db,
        email_service=email_service,
    )

    # Send emails
    print("📧 Sending update emails...")
    if config.test_mode:
        print(f"   Mode: TEST (sending to {settings.test_email_recipient})")
    else:
        eligible_count = len(update_service.get_eligible_users())
        print(f"   Mode: PRODUCTION (sending to {eligible_count} users)")
        total_batches = (eligible_count + config.batch_size - 1) // config.batch_size
        estimated_time = (total_batches - 1) * config.batch_delay_seconds
        print(f"   Estimated batches: {total_batches}")
        print(f"   Estimated time: {estimated_time:.0f} seconds")

    try:
        summary = update_service.send_update_email(config)
        print("✅ All emails processed!")
        print(format_summary(summary))

        if summary.failed > 0:
            print(f"⚠️  {summary.failed} emails failed to send")
            sys.exit(1)
    except Exception as e:
        print(f"❌ Error sending emails: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    main()
