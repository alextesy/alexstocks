"""User profile and settings API routes."""

import logging
from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import case, func
from sqlalchemy.orm import Session

from app.config import settings
from app.db.models import Ticker
from app.db.session import get_db
from app.models.dto import (
    UserProfileResponseDTO,
    UserProfileUpdateDTO,
    UserTickerFollowCreateDTO,
    UserTickerFollowDTO,
)
from app.repos.user_repo import UserRepository
from app.services.auth_service import get_auth_service
from app.services.user_notification_channel_service import (
    ensure_email_notification_channel,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/users", tags=["users"])


def get_current_user_id(
    session_token: Annotated[str | None, Cookie()] = None,
    db: Session = Depends(get_db),
) -> int:
    """Get current authenticated user ID from session token."""
    if not session_token:
        raise HTTPException(status_code=401, detail="Not authenticated")

    auth_service = get_auth_service()
    user = auth_service.get_current_user(db, session_token)

    if not user:
        raise HTTPException(status_code=401, detail="Invalid session")

    return user.id


@router.get("/me", response_model=UserProfileResponseDTO)
async def get_current_user_profile(
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """Get current user's profile and notification defaults.

    Returns:
        UserProfileResponseDTO with profile data and notification defaults
    """
    repo = UserRepository(db)
    user = repo.get_user_by_id(user_id)

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Get profile (create default if missing)
    profile = repo.get_profile(user_id)
    if not profile:
        # Create default profile
        from app.models.dto import UserProfileCreateDTO

        profile_dto = UserProfileCreateDTO(
            user_id=user_id,
            timezone="UTC",
            preferences={},
        )
        profile = repo.create_profile(profile_dto)
        db.commit()
        profile = repo.get_profile(user_id)
        if not profile:
            raise HTTPException(status_code=500, detail="Failed to create profile")

    # Extract notification defaults from preferences
    notification_defaults = {}
    if profile.preferences and isinstance(profile.preferences, dict):
        notification_defaults = profile.preferences.get("notification_defaults", {})

    return UserProfileResponseDTO(
        id=user.id,
        email=user.email,
        nickname=profile.display_name,
        avatar_url=profile.avatar_url,
        timezone=profile.timezone,
        notification_defaults=notification_defaults,
        created_at=user.created_at,
        updated_at=profile.updated_at,
    )


@router.put("/me", response_model=UserProfileResponseDTO)
async def update_current_user_profile(
    update_data: UserProfileUpdateDTO,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """Update current user's profile.

    Logs the received data for debugging.

    Updates nickname, avatar URL, timezone, and notification defaults.
    Nickname uniqueness is enforced.

    Args:
        update_data: Profile update data
        user_id: Current user ID (from dependency)
        db: Database session

    Returns:
        Updated UserProfileResponseDTO

    Raises:
        400: If nickname is already taken
        404: If user or profile not found
    """
    repo = UserRepository(db)
    user = repo.get_user_by_id(user_id)

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Ensure profile exists - get the actual model object, not DTO
    from app.db.models import UserProfile

    profile = db.get(UserProfile, user_id)
    if not profile:
        # Create default profile first
        from app.models.dto import UserProfileCreateDTO

        profile_dto = UserProfileCreateDTO(
            user_id=user_id,
            timezone="UTC",
            preferences={},
        )
        repo.create_profile(profile_dto)
        db.commit()
        # Re-fetch the profile after creation
        profile = db.get(UserProfile, user_id)
        if not profile:
            raise HTTPException(status_code=500, detail="Failed to create profile")

    try:
        # Update profile
        updated_profile = repo.update_profile(
            user_id=user_id,
            nickname=update_data.nickname,
            avatar_url=update_data.avatar_url,
            timezone=update_data.timezone,
            notification_defaults=update_data.notification_defaults,
        )

        if not updated_profile:
            raise HTTPException(status_code=404, detail="Profile not found")

        if update_data.notification_defaults is not None:
            # Flush profile update first to ensure it's in the session
            db.flush()
            # Pass the profile object to ensure it's used in sync
            ensure_email_notification_channel(
                db,
                user_id=user.id,
                email=user.email,
                preferences=update_data.notification_defaults,
            )
            # Ensure sync changes are flushed
            db.flush()

        db.commit()

        # Refresh the profile model object to get the latest data after sync
        # The sync in ensure_email_notification_channel may have updated the profile
        db.refresh(profile)

        # Get fresh DTO from the refreshed model
        updated_profile = repo.get_profile(user_id)
        if not updated_profile:
            raise HTTPException(
                status_code=404, detail="Profile not found after update"
            )

        # Extract notification defaults from refreshed profile
        notification_defaults = {}
        if updated_profile.preferences and isinstance(
            updated_profile.preferences, dict
        ):
            notification_defaults = updated_profile.preferences.get(
                "notification_defaults", {}
            )

        logger.info(
            "user_profile_updated",
            extra={
                "user_id": user_id,
                "updated_fields": {
                    "nickname": update_data.nickname is not None,
                    "avatar_url": update_data.avatar_url is not None,
                    "timezone": update_data.timezone is not None,
                    "notification_defaults": update_data.notification_defaults
                    is not None,
                },
            },
        )

        return UserProfileResponseDTO(
            id=user.id,
            email=user.email,
            nickname=updated_profile.display_name,
            avatar_url=updated_profile.avatar_url,
            timezone=updated_profile.timezone,
            notification_defaults=notification_defaults,
            created_at=user.created_at,
            updated_at=updated_profile.updated_at,
        )

    except ValueError as e:
        # Nickname uniqueness violation or validation error
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e)) from e


# Watchlist Management Endpoints


class TickerFollowRequest(BaseModel):
    """Request model for adding a ticker follow."""

    ticker: str
    notify_on_signals: bool = True
    notify_on_price_change: bool = False
    price_change_threshold: float | None = None


class TickerReorderRequest(BaseModel):
    """Request model for reordering ticker follows."""

    ticker_orders: dict[str, int]  # Mapping of ticker symbol to order position


@router.get("/me/follows", response_model=list[UserTickerFollowDTO])
async def get_user_ticker_follows(
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
    limit: int = 100,
    offset: int = 0,
):
    """Get list of tickers the user follows, in stored order.

    Args:
        user_id: Current user ID (from dependency)
        db: Database session
        limit: Maximum number of results (capped at MAX_LIMIT_TICKERS)
        offset: Pagination offset

    Returns:
        List of UserTickerFollowDTO in order
    """
    repo = UserRepository(db)
    max_limit = min(limit, settings.USER_MAX_TICKER_FOLLOWS)
    follows = repo.get_ticker_follows(user_id, limit=max_limit, offset=offset)
    return follows


@router.post("/me/follows", response_model=UserTickerFollowDTO, status_code=201)
async def add_ticker_follow(
    request: TickerFollowRequest,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """Add a ticker to user's watchlist.

    Validates ticker exists in master list, respects max-follow limit,
    and prevents duplicates.

    Args:
        request: Ticker follow request data
        user_id: Current user ID (from dependency)
        db: Database session

    Returns:
        Created UserTickerFollowDTO

    Raises:
        400: If ticker doesn't exist, limit reached, or validation fails
        404: If ticker symbol not found in master list
    """
    repo = UserRepository(db)

    # Check current follow count
    current_follows = repo.get_ticker_follows(
        user_id, limit=settings.USER_MAX_TICKER_FOLLOWS
    )
    if len(current_follows) >= settings.USER_MAX_TICKER_FOLLOWS:
        raise HTTPException(
            status_code=400,
            detail=f"Maximum follow limit ({settings.USER_MAX_TICKER_FOLLOWS}) reached",
        )

    # Validate ticker exists in master list
    ticker = db.query(Ticker).filter(Ticker.symbol == request.ticker.upper()).first()
    if not ticker:
        raise HTTPException(
            status_code=404,
            detail=f"Ticker '{request.ticker}' not found in master list",
        )

    # Check for duplicate
    existing = repo.get_ticker_follow(user_id, request.ticker.upper())
    if existing:
        raise HTTPException(
            status_code=400, detail=f"Already following ticker '{request.ticker}'"
        )

    # Create follow
    follow_dto = UserTickerFollowCreateDTO(
        user_id=user_id,
        ticker=request.ticker.upper(),
        notify_on_signals=request.notify_on_signals,
        notify_on_price_change=request.notify_on_price_change,
        price_change_threshold=request.price_change_threshold,
    )

    try:
        follow = repo.create_ticker_follow(follow_dto)
        db.commit()

        logger.info(
            "ticker_follow_added",
            extra={"user_id": user_id, "ticker": request.ticker.upper()},
        )

        return follow
    except Exception as e:
        db.rollback()
        logger.error(
            "ticker_follow_add_error",
            extra={"user_id": user_id, "ticker": request.ticker, "error": str(e)},
        )
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.delete("/me/follows/{symbol}", status_code=204)
async def remove_ticker_follow(
    symbol: str,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """Remove a ticker from user's watchlist.

    Args:
        symbol: Ticker symbol to remove
        user_id: Current user ID (from dependency)
        db: Database session

    Returns:
        204 No Content on success

    Raises:
        404: If ticker follow not found
    """
    repo = UserRepository(db)
    deleted = repo.delete_ticker_follow(user_id, symbol.upper())

    if not deleted:
        raise HTTPException(
            status_code=404, detail=f"Ticker follow '{symbol}' not found"
        )

    db.commit()

    logger.info(
        "ticker_follow_removed",
        extra={"user_id": user_id, "ticker": symbol.upper()},
    )

    return None


@router.patch("/me/follows/reorder", response_model=list[UserTickerFollowDTO])
async def reorder_ticker_follows(
    request: TickerReorderRequest,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """Reorder ticker follows for a user.

    Args:
        request: Mapping of ticker symbols to new order positions
        user_id: Current user ID (from dependency)
        db: Database session

    Returns:
        List of updated ticker follow DTOs in new order

    Raises:
        400: If validation fails or ticker not found
    """
    repo = UserRepository(db)

    # Validate all tickers belong to user
    user_follows = repo.get_ticker_follows(
        user_id, limit=settings.USER_MAX_TICKER_FOLLOWS
    )
    user_tickers = {f.ticker for f in user_follows}
    requested_tickers = set(request.ticker_orders.keys())

    if not requested_tickers.issubset(user_tickers):
        missing = requested_tickers - user_tickers
        raise HTTPException(
            status_code=400,
            detail=f"Tickers not in watchlist: {', '.join(missing)}",
        )

    try:
        updated_follows = repo.reorder_ticker_follows(user_id, request.ticker_orders)
        db.commit()

        logger.info(
            "ticker_follows_reordered",
            extra={"user_id": user_id, "ticker_count": len(request.ticker_orders)},
        )

        return updated_follows
    except Exception as e:
        db.rollback()
        logger.error(
            "ticker_follows_reorder_error",
            extra={"user_id": user_id, "error": str(e)},
        )
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.get("/me/follows/search", response_model=list[dict])
async def search_tickers(
    q: str,
    limit: int = 20,
    db: Session = Depends(get_db),
    _: int = Depends(get_current_user_id),  # Require auth but don't use user_id
):
    """Search tickers for typeahead/picker component.

    Args:
        q: Search query (symbol or name)
        limit: Maximum results (default 20)
        db: Database session
        _: Auth dependency (ensures user is logged in)

    Returns:
        List of ticker objects with symbol, name, exchange
    """
    if not q or len(q.strip()) < 1:
        return []

    normalized_query = q.strip()
    upper_query = normalized_query.upper()
    search_term = f"%{upper_query}%"
    prefix_term = f"{upper_query}%"
    max_limit = min(limit, 50)

    relevance_order = case(
        (func.lower(Ticker.symbol) == upper_query.lower(), 0),
        (Ticker.symbol.ilike(prefix_term), 1),
        (Ticker.symbol.ilike(search_term), 2),
        else_=3,
    )

    tickers = (
        db.query(Ticker)
        .filter(Ticker.symbol.ilike(search_term) | Ticker.name.ilike(search_term))
        .order_by(relevance_order, Ticker.symbol)
        .limit(max_limit)
        .all()
    )

    return [
        {
            "symbol": t.symbol,
            "name": t.name,
            "exchange": t.exchange,
        }
        for t in tickers
    ]
