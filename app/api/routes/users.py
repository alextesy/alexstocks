"""User profile and settings API routes."""

import logging
from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.dto import UserProfileResponseDTO, UserProfileUpdateDTO
from app.repos.user_repo import UserRepository
from app.services.auth_service import get_auth_service

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

    # Ensure profile exists
    profile = repo.get_profile(user_id)
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

        db.commit()

        # Extract notification defaults
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
