"""
User API Routes
Handles all user-related endpoints
"""
from fastapi import APIRouter, HTTPException, status
from typing import List, Optional

from app.crud.user import CRUDUser
from app.schemas.user import UserBase, User
from app.core.supabase import supabase
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/users", tags=["users"])
crud_user = CRUDUser(supabase)


# -------------------------
# CREATE USER
# -------------------------
@router.post("/", status_code=201)
def create_user(user: dict):
    """Create a new user"""
    try:
        return crud_user.create(user)
    except Exception as e:
        logger.error(f"Error creating user: {e}")
        raise HTTPException(status_code=400, detail=str(e))


# -------------------------
# GET USER BY ID
# -------------------------
@router.get("/{user_id}")
def get_user(
    user_id: int,
    current_user_id: int,
    is_admin: bool = False
):
    """Get a user by ID"""
    try:
        user = crud_user.get_by_id(user_id, current_user_id, is_admin)

        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        return user

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting user: {e}")
        raise HTTPException(status_code=403, detail=str(e))


# -------------------------
# GET MULTIPLE USERS (ADMIN)
# -------------------------
@router.get("/")
def get_users(
    skip: int = 0,
    limit: int = 20,
    is_admin: bool = False
):
    """Get multiple users (admin only)"""
    try:
        return crud_user.get_multi(skip, limit, is_admin)
    except Exception as e:
        logger.error(f"Error getting users: {e}")
        raise HTTPException(status_code=403, detail=str(e))


# -------------------------
# UPDATE USER
# -------------------------
@router.put("/{user_id}")
def update_user(
    user_id: int,
    user_data: dict,
    current_user_id: int,
    is_admin: bool = False
):
    """Update a user"""
    try:
        updated = crud_user.update(user_id, user_data, current_user_id, is_admin)

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
def delete_user(
    user_id: int,
    current_user_id: int,
    is_admin: bool = False
):
    """Soft delete a user (deactivate)"""
    try:
        success = crud_user.delete(user_id, current_user_id, is_admin)

        if not success:
            raise HTTPException(status_code=404, detail="User not found")

        return {"message": "User deactivated successfully"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting user: {e}")
        raise HTTPException(status_code=403, detail=str(e))


# -------------------------
# GET USER BY EMAIL
# -------------------------
@router.get("/email/{email}")
def get_user_by_email(email: str):
    """Get a user by email"""
    try:
        user = crud_user.get_by_email(email)

        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        # Don't return password_hash in response
        user.pop("password_hash", None)
        return user

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting user by email: {e}")
        raise HTTPException(status_code=500, detail=str(e))
