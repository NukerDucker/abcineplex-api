"""
User API Routes
Handles all user-related endpoints.
Optimized with global exception handlers and efficient dependencies.
"""
from fastapi import APIRouter, Depends
from typing import List

from app.crud.user import CRUDUser
from app.core.supabase import supabase
from app.core.security import get_current_user, CurrentUser
from app.core.exceptions import NotFoundException, UnauthorizedException

router = APIRouter(prefix="/api/users", tags=["users"])
crud_user = CRUDUser(supabase)


@router.get("/me")
async def get_current_user_profile(
    current_user: CurrentUser = Depends(get_current_user),
):
    """Get current user's profile with admin status from users table"""
    import asyncio
    try:
        response = await asyncio.to_thread(
            lambda: supabase.table("users")
                .select("user_id, email, user_name, full_name, loyalty_points, is_admin, is_active")
                .eq("email", current_user.email)
                .maybe_single()
                .execute()
        )
        if response.data:
            return response.data
        # Fallback to current user info
        return {
            "user_id": current_user.user_id,
            "email": current_user.email,
            "user_name": current_user.user_name,
            "full_name": current_user.full_name,
            "loyalty_points": current_user.loyalty_points,
            "is_admin": current_user.is_admin,
            "is_active": True
        }
    except Exception as e:
        # Fallback if query fails
        return {
            "user_id": current_user.user_id,
            "email": current_user.email,
            "user_name": current_user.user_name,
            "full_name": current_user.full_name,
            "loyalty_points": current_user.loyalty_points,
            "is_admin": current_user.is_admin,
            "is_active": True
        }


@router.get("/")
async def get_users(
    skip: int = 0,
    limit: int = 20,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Get multiple users (admin only)"""
    if not current_user.is_admin:
        raise UnauthorizedException()
    return await crud_user.get_multi(skip, limit, is_admin=True)


@router.get("/email/{email}")
async def get_user_by_email(
    email: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Get a user by email (admin only)"""
    if not current_user.is_admin:
        raise UnauthorizedException()

    user = await crud_user.get_by_email(email)
    if not user:
        raise NotFoundException("User", email)

    return user


@router.get("/{user_id}")
async def get_user(
    user_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Get a user by ID"""
    user = await crud_user.get_by_id(
        user_id,
        current_user_id=current_user.user_id,
        is_admin=current_user.is_admin,
    )

    if not user:
        raise NotFoundException("User", user_id)

    return user


@router.put("/{user_id}")
async def update_user(
    user_id: str,
    user_data: dict,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Update a user"""
    updated = await crud_user.update(
        user_id,
        user_data,
        current_user_id=current_user.user_id,
        is_admin=current_user.is_admin,
    )

    if not updated:
        raise NotFoundException("User", user_id)

    return updated


@router.delete("/{user_id}")
async def delete_user(
    user_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Soft delete a user (deactivate)"""
    success = await crud_user.delete(
        user_id,
        current_user_id=current_user.user_id,
        is_admin=current_user.is_admin,
    )

    if not success:
        raise NotFoundException("User", user_id)

    return {"message": "User deactivated successfully"}
