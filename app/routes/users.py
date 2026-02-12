"""
User API Routes
Handles all user-related endpoints.
Authentication is handled via Supabase JWT tokens.
"""
from fastapi import APIRouter, HTTPException, status, Depends
from typing import List, Optional

from app.crud.user import CRUDUser
from app.core.supabase import supabase
from app.core.security import get_current_user
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/users", tags=["users"])
crud_user = CRUDUser(supabase)


# -------------------------
# GET MULTIPLE USERS (ADMIN)
# -------------------------
@router.get("/")
async def get_users(
    skip: int = 0,
    limit: int = 20,
    is_admin: bool = False,
    current_user: dict = Depends(get_current_user),
):
    """Get multiple users (admin only)"""
    try:
        return await crud_user.get_multi(skip, limit, is_admin=is_admin or current_user["is_admin"])
    except Exception as e:
        logger.error(f"Error getting users: {e}")
        raise HTTPException(status_code=403, detail=str(e))


# -------------------------
# GET USER BY EMAIL
# -------------------------
@router.get("/email/{email}")
async def get_user_by_email(
    email: str,
    is_admin: bool = False,
    current_user: dict = Depends(get_current_user),
):
    """Get a user by email (admin only)"""
    try:
        if not (is_admin or current_user["is_admin"]):
            raise HTTPException(status_code=403, detail="Not authorized")

        user = await crud_user.get_by_email(email)

        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        user.pop("password_hash", None)
        return user

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting user by email: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# -------------------------
# GET USER BY ID
# -------------------------
@router.get("/{user_id}")
async def get_user(
    user_id: str,
    is_admin: bool = False,
    current_user: dict = Depends(get_current_user),
):
    """Get a user by ID"""
    try:
        user = await crud_user.get_by_id(
            user_id,
            current_user_id=current_user["supabase_id"],
            is_admin=is_admin or current_user["is_admin"],
        )

        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        return user

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting user: {e}")
        raise HTTPException(status_code=403, detail=str(e))


# -------------------------
# UPDATE USER
# -------------------------
@router.put("/{user_id}")
async def update_user(
    user_id: str,
    user_data: dict,
    is_admin: bool = False,
    current_user: dict = Depends(get_current_user),
):
    """Update a user"""
    try:
        updated = await crud_user.update(
            user_id,
            user_data,
            current_user_id=current_user["supabase_id"],
            is_admin=is_admin or current_user["is_admin"],
        )

        if not updated:
            raise HTTPException(status_code=404, detail="User not found or no valid fields to update")

        return updated

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating user: {e}")
        raise HTTPException(status_code=403, detail=str(e))


# -------------------------
# DELETE USER (SOFT DELETE)
# -------------------------
@router.delete("/{user_id}")
async def delete_user(
    user_id: str,
    is_admin: bool = False,
    current_user: dict = Depends(get_current_user),
):
    """Soft delete a user (deactivate)"""
    try:
        success = await crud_user.delete(
            user_id,
            current_user_id=current_user["supabase_id"],
            is_admin=is_admin or current_user["is_admin"],
        )

        if not success:
            raise HTTPException(status_code=404, detail="User not found")

        return {"message": "User deactivated successfully"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting user: {e}")
        raise HTTPException(status_code=403, detail=str(e))
