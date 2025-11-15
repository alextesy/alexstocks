"""Email-related API routes for unsubscribe and webhooks."""

import json
import logging
from urllib.parse import unquote_plus

import boto3
from fastapi import APIRouter, Depends, Query, Request, status
from fastapi.responses import HTMLResponse, PlainTextResponse
from sqlalchemy.orm import Session

from app.config import settings
from app.db.session import get_db
from app.repos.user_repo import UserRepository
from app.services.email_utils import verify_unsubscribe_token

logger = logging.getLogger(__name__)

router = APIRouter(tags=["email"])

# SNS client for message verification
_sns_client = None


def get_sns_client():
    """Get or create SNS client."""
    global _sns_client
    if _sns_client is None:
        _sns_client = boto3.client("sns", region_name=settings.aws_ses_region)
    return _sns_client


@router.get("/unsubscribe", response_class=HTMLResponse)
async def unsubscribe(
    request: Request,
    token: str = Query(..., description="Unsubscribe token"),
    db: Session = Depends(get_db),
):
    """Handle unsubscribe requests from email links.

    Args:
        request: FastAPI request object
        token: JWT unsubscribe token from email link
        db: Database session

    Returns:
        HTML confirmation page
    """
    try:
        # Decode URL-encoded token
        decoded_token = unquote_plus(token)
        # Verify token and extract user_id
        user_id = verify_unsubscribe_token(decoded_token)
    except ValueError as e:
        logger.warning(
            "Invalid unsubscribe token",
            extra={"error": str(e)},
        )
        # Return error page
        from fastapi.templating import Jinja2Templates

        templates = Jinja2Templates(directory="app/templates")

        def url_string(url_obj) -> str:
            """Convert URL object to string safely for Jinja2 templates."""
            if url_obj is None:
                return ""
            return str(url_obj)

        templates.env.filters["url_string"] = url_string
        templates.env.globals["settings"] = settings
        return templates.TemplateResponse(
            "unsubscribe_error.html",
            {
                "request": request,
                "error_message": "Invalid or expired unsubscribe link. Please contact support if you need assistance.",
            },
        )

    # Find user's email notification channel and disable it
    user_repo = UserRepository(db)
    channels = user_repo.get_notification_channels(user_id)
    email_channel = None
    for channel in channels:
        if channel.channel_type == "email":
            email_channel = channel
            break

    if not email_channel:
        logger.warning(
            "No email channel found for unsubscribe",
            extra={"user_id": user_id},
        )
        # Still show success page to avoid revealing user existence
        from fastapi.templating import Jinja2Templates

        templates = Jinja2Templates(directory="app/templates")

        def url_string(url_obj) -> str:
            """Convert URL object to string safely for Jinja2 templates."""
            if url_obj is None:
                return ""
            return str(url_obj)

        templates.env.filters["url_string"] = url_string
        templates.env.globals["settings"] = settings
        return templates.TemplateResponse(
            "unsubscribe.html",
            {
                "request": request,
                "success": True,
            },
        )

    # Disable the email channel
    updated_channel = user_repo.update_notification_channel(
        channel_id=email_channel.id,
        is_enabled=False,
    )

    if updated_channel:
        # Also update user profile notification_defaults to disable daily briefing
        profile = user_repo.get_profile(user_id)
        if profile:
            # Get current notification_defaults or create empty dict
            current_defaults = {}
            if profile.preferences and isinstance(profile.preferences, dict):
                current_defaults = profile.preferences.get(
                    "notification_defaults", {}
                ).copy()
            else:
                current_defaults = {}

            # Update notify_on_daily_briefing to False
            current_defaults["notify_on_daily_briefing"] = False

            # Update profile with new notification_defaults
            user_repo.update_profile(
                user_id=user_id,
                notification_defaults=current_defaults,
            )

        logger.info(
            "User unsubscribed from emails",
            extra={
                "user_id": user_id,
                "channel_id": email_channel.id,
                "email": email_channel.channel_value,
            },
        )
        db.commit()
    else:
        logger.error(
            "Failed to update notification channel",
            extra={"user_id": user_id, "channel_id": email_channel.id},
        )

    # Return success page
    from fastapi.templating import Jinja2Templates

    templates = Jinja2Templates(directory="app/templates")

    def url_string(url_obj) -> str:
        """Convert URL object to string safely for Jinja2 templates."""
        if url_obj is None:
            return ""
        return str(url_obj)

    templates.env.filters["url_string"] = url_string
    templates.env.globals["settings"] = settings
    return templates.TemplateResponse(
        "unsubscribe.html",
        {
            "request": request,
            "success": True,
        },
    )


@router.post("/api/webhooks/ses")
async def ses_webhook(
    request: Request,
    db: Session = Depends(get_db),
):
    """Handle AWS SES bounce notifications via SNS.

    This endpoint processes:
    - SNS subscription confirmation requests
    - SES bounce notifications

    Args:
        request: FastAPI request object
        db: Database session

    Returns:
        200 OK with appropriate response
    """
    try:
        body = await request.body()
        payload = json.loads(body.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        logger.error(
            "Invalid webhook payload",
            extra={"error": str(e)},
        )
        return PlainTextResponse(
            "Invalid payload", status_code=status.HTTP_400_BAD_REQUEST
        )

    message_type = payload.get("Type")
    if not message_type:
        logger.warning("Missing Type in SNS message", extra={"payload": payload})
        return PlainTextResponse(
            "Missing Type", status_code=status.HTTP_400_BAD_REQUEST
        )

    # Handle SNS subscription confirmation
    if message_type == "SubscriptionConfirmation":
        subscribe_url = payload.get("SubscribeURL")
        if subscribe_url:
            logger.info(
                "SNS subscription confirmation received",
                extra={"topic_arn": payload.get("TopicArn")},
            )
            # Confirm subscription by visiting the URL
            try:
                import urllib.request

                urllib.request.urlopen(subscribe_url).read()
                logger.info("SNS subscription confirmed")
                return PlainTextResponse("Subscription confirmed", status_code=200)
            except Exception as e:
                logger.error(
                    "Failed to confirm SNS subscription",
                    extra={"error": str(e), "url": subscribe_url},
                )
                return PlainTextResponse(
                    "Failed to confirm subscription",
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                )
        return PlainTextResponse(
            "No SubscribeURL", status_code=status.HTTP_400_BAD_REQUEST
        )

    # Handle notification (bounce/complaint)
    if message_type == "Notification":
        try:
            # Note: SNS message signature verification would require downloading
            # the certificate from SigningCertURL and verifying the signature.
            # For now, we rely on HTTPS and proper AWS IAM/security groups.
            # In production, consider implementing full signature verification.
            # Basic validation: ensure required fields are present
            if not payload.get("Signature") or not payload.get("SigningCertURL"):
                logger.warning("SNS notification missing signature fields")
                # Still process but log warning

            # Parse the message
            message_str = payload.get("Message")
            if not message_str:
                logger.warning("Missing Message in SNS notification")
                return PlainTextResponse("Missing Message", status_code=400)

            try:
                message = json.loads(message_str)
            except json.JSONDecodeError:
                logger.error(
                    "Invalid JSON in SNS message", extra={"message": message_str}
                )
                return PlainTextResponse("Invalid message JSON", status_code=400)

            notification_type = message.get("notificationType")
            if notification_type == "Bounce":
                return await _handle_bounce_notification(message, db)
            elif notification_type == "Complaint":
                # Skip complaint handling for now as requested
                logger.info(
                    "Complaint notification received (skipped)",
                    extra={"message": message},
                )
                return PlainTextResponse(
                    "Complaint received (not processed)", status_code=200
                )
            else:
                logger.info(
                    "Unknown notification type",
                    extra={"type": notification_type, "message": message},
                )
                return PlainTextResponse("Unknown notification type", status_code=200)

        except Exception as e:
            logger.error(
                "Error processing SNS notification",
                extra={"error": str(e)},
                exc_info=True,
            )
            return PlainTextResponse(
                "Internal server error",
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    # Unknown message type
    logger.warning("Unknown SNS message type", extra={"type": message_type})
    return PlainTextResponse("Unknown message type", status_code=200)


async def _handle_bounce_notification(message: dict, db: Session) -> PlainTextResponse:
    """Handle a bounce notification from SES.

    Args:
        message: Parsed bounce notification message
        db: Database session

    Returns:
        PlainTextResponse with status
    """
    try:
        bounce = message.get("bounce", {})
        bounce_type = bounce.get("bounceType", "Unknown")
        bounce_subtype = bounce.get("bounceSubType", "Unknown")
        bounced_recipients = bounce.get("bouncedRecipients", [])

        # Determine if this is a permanent bounce
        is_permanent = bounce_type == "Permanent"
        bounce_type_label = f"{bounce_type} ({bounce_subtype})"

        user_repo = UserRepository(db)
        processed_count = 0

        for recipient in bounced_recipients:
            email = recipient.get("emailAddress")
            if not email:
                continue

            try:
                updated_channel = user_repo.mark_email_bounced(
                    email=email,
                    bounce_type=bounce_type_label,
                    disable_channel=is_permanent,
                )

                if updated_channel:
                    processed_count += 1
                    logger.info(
                        "Email bounce processed",
                        extra={
                            "email": email,
                            "bounce_type": bounce_type_label,
                            "is_permanent": is_permanent,
                            "channel_id": updated_channel.id,
                        },
                    )
                else:
                    logger.warning(
                        "Email bounce received but channel not found",
                        extra={"email": email},
                    )
            except Exception as e:
                logger.error(
                    "Error processing bounce for email",
                    extra={"email": email, "error": str(e)},
                    exc_info=True,
                )

        if processed_count > 0:
            db.commit()
            logger.info(
                "Bounce notification processed",
                extra={
                    "processed_count": processed_count,
                    "total_recipients": len(bounced_recipients),
                    "bounce_type": bounce_type_label,
                },
            )
        else:
            db.rollback()

        return PlainTextResponse("Bounce processed", status_code=200)

    except Exception as e:
        logger.error(
            "Error handling bounce notification",
            extra={"error": str(e), "message": message},
            exc_info=True,
        )
        db.rollback()
        return PlainTextResponse(
            "Error processing bounce",
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
