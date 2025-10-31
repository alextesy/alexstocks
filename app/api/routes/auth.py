"""Authentication routes for Google OAuth."""

import logging
import secrets
from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.config import settings
from app.db.session import get_db
from app.services.auth_service import (
    AuthError,
    BlockedAccountError,
    InvalidCredentialsError,
    MissingProfileDataError,
    NonGmailDomainError,
    get_auth_service,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    """Render login page with Google Sign-In button."""
    from fastapi.templating import Jinja2Templates

    templates = Jinja2Templates(directory="app/templates")

    # Generate CSRF state token
    state = secrets.token_urlsafe(32)

    # Store state in session (simplified - in production use Redis or secure session)
    # For now, we'll pass it through the OAuth flow

    auth_service = get_auth_service()
    google_oauth_url = auth_service.get_google_oauth_url(state=state)

    return templates.TemplateResponse(
        "auth/login.html",
        {
            "request": request,
            "google_oauth_url": google_oauth_url,
            "state": state,
        },
    )


@router.get("/callback")
async def auth_callback(
    request: Request,
    code: str = Query(..., description="Authorization code from Google"),
    state: str = Query(None, description="CSRF state token"),
    error: str = Query(None, description="Error from OAuth provider"),
    db: Session = Depends(get_db),
):
    """Handle OAuth callback from Google.

    This endpoint:
    1. Exchanges authorization code for access token
    2. Fetches user profile from Google
    3. Validates Gmail domain
    4. Creates or retrieves user record
    5. Issues session token
    """
    # Handle OAuth errors
    if error:
        logger.error(
            "oauth_callback_error",
            extra={"error": error},
        )
        return RedirectResponse(
            url=f"/auth/login?error=oauth_error",
            status_code=302,
        )

    auth_service = get_auth_service()

    try:
        # Exchange code for token
        token_response = await auth_service.exchange_code_for_token(code)
        access_token = token_response.get("access_token")
        refresh_token = token_response.get("refresh_token")

        if not access_token:
            raise InvalidCredentialsError("No access token received")

        # Fetch user info
        user_info = await auth_service.get_user_info(access_token)

        email = user_info.get("email")
        google_id = user_info.get("id")
        name = user_info.get("name")
        picture = user_info.get("picture")

        # Validate Gmail domain
        auth_service.validate_gmail_domain(email)

        # Get or create user
        user = auth_service.get_or_create_user(
            db=db,
            google_id=google_id,
            email=email,
            name=name,
            picture=picture,
            refresh_token=refresh_token,
        )

        # Create session token
        session_token = auth_service.create_session_token(
            user_id=user.id,
            email=user.email,
        )

        # Redirect to home with session cookie
        response = RedirectResponse(url="/", status_code=302)
        response.set_cookie(
            key="session_token",
            value=session_token,
            max_age=settings.session_max_age_seconds,
            httponly=True,
            secure=settings.environment == "production",
            samesite="lax",
        )

        logger.info(
            "user_authenticated",
            extra={"user_id": user.id, "email": user.email},
        )

        return response

    except NonGmailDomainError:
        logger.warning("non_gmail_login_blocked")
        return RedirectResponse(
            url="/auth/login?error=non_gmail",
            status_code=302,
        )
    except BlockedAccountError:
        logger.warning("blocked_account_login")
        return RedirectResponse(
            url="/auth/login?error=account_blocked",
            status_code=302,
        )
    except MissingProfileDataError:
        logger.error("missing_profile_data")
        return RedirectResponse(
            url="/auth/login?error=missing_data",
            status_code=302,
        )
    except AuthError as e:
        logger.error(
            "auth_error",
            extra={"error": str(e)},
        )
        return RedirectResponse(
            url="/auth/login?error=auth_failed",
            status_code=302,
        )
    except Exception as e:
        logger.exception(
            "unexpected_auth_error",
            extra={"error": str(e)},
        )
        return RedirectResponse(
            url="/auth/login?error=unexpected",
            status_code=302,
        )


@router.get("/logout")
async def logout(request: Request):
    """Log out the current user by invalidating session cookie."""
    response = RedirectResponse(url="/", status_code=302)
    response.delete_cookie(key="session_token")

    logger.info("user_logged_out")

    return response


@router.get("/me")
async def get_current_user_info(
    session_token: Annotated[str | None, Cookie()] = None,
    db: Session = Depends(get_db),
):
    """Get current authenticated user information."""
    if not session_token:
        raise HTTPException(status_code=401, detail="Not authenticated")

    auth_service = get_auth_service()
    user = auth_service.get_current_user(db, session_token)

    if not user:
        raise HTTPException(status_code=401, detail="Invalid session")

    return {
        "id": user.id,
        "email": user.email,
        "name": user.name,
        "picture": user.picture,
        "created_at": user.created_at.isoformat(),
        "last_login_at": user.last_login_at.isoformat(),
    }

