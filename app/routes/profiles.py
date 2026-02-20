"""
User Profile API Routes
Handles user profile information endpoints
"""
from fastapi import APIRouter, Depends
from typing import List
from uuid import UUID

from app.crud.profile import CRUDProfile
from app.schemas.profile import Profile, ProfileUpdate
from app.core.supabase import supabase
from app.core.security import get_current_user, CurrentUser
from app.core.exceptions import NotFoundException, UnauthorizedException

router = APIRouter(prefix="/api/profiles", tags=["profiles"])
crud_profile = CRUDProfile(supabase)


@router.get("/", response_model=List[Profile])
async def get_profiles(
    skip: int = 0,
    limit: int = 20,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Get all user profiles (admin only)"""
    return await crud_profile.get_profiles(skip, limit, is_admin=current_user.is_admin)


@router.get("/{user_id}", response_model=Profile)
async def get_profile(
    user_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Get user profile by user ID"""
    try:
        profile = await crud_profile.get_profile(
            UUID(user_id),
            UUID(current_user.user_id),
            is_admin=current_user.is_admin
        )
    except UnauthorizedException:
        raise NotFoundException("Profile", user_id)

    if not profile:
        raise NotFoundException("Profile", user_id)
    return profile


@router.put("/{user_id}", response_model=Profile)
async def update_profile(
    user_id: str,
    profile_in: ProfileUpdate,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Update user profile (user or admin)"""
    try:
        updated = await crud_profile.update_profile(
            UUID(user_id),
            profile_in,
            UUID(current_user.user_id),
            is_admin=current_user.is_admin
        )
    except UnauthorizedException:
        raise NotFoundException("You are not authorized to update this profile")

    if not updated:
        raise NotFoundException("Profile", user_id)
    return updated


@router.get("/{user_id}/loyalty-points")
async def get_loyalty_points(
    user_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Get user's loyalty points"""
    try:
        points = await crud_profile.get_loyalty_points(
            UUID(user_id),
            UUID(current_user.user_id),
            is_admin=current_user.is_admin
        )
    except UnauthorizedException:
        raise NotFoundException("You are not authorized to view these loyalty points")

    if points is None:
        raise NotFoundException("Profile", user_id)
    return {"loyalty_points": points}


@router.post("/{user_id}/loyalty-points/add")
async def add_loyalty_points(
    user_id: str,
    points: int,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Add loyalty points to user (admin only)"""
    if not current_user.is_admin:
        raise UnauthorizedException()

    updated = await crud_profile.add_loyalty_points(
        UUID(user_id),
        points,
        is_admin=True
    )

    if not updated:
        raise NotFoundException("Profile", user_id)
    return updated


@router.post("/{user_id}/loyalty-points/redeem")
async def redeem_loyalty_points(
    user_id: str,
    points: int,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Redeem loyalty points (user or admin)"""
    redeemed = await crud_profile.redeem_loyalty_points(
        UUID(user_id),
        points,
        UUID(current_user.user_id),
        is_admin=current_user.is_admin
    )

    if not redeemed:
        raise NotFoundException("Profile", user_id)
    return redeemed
