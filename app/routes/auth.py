"""
Auth API Routes
Handles authenticated user endpoints.
Authentication is handled client-side via Supabase Auth.
The backend only verifies Supabase access tokens.
"""
from fastapi import APIRouter, HTTPException, status, Depends

from app.schemas.auth import UserResponse
from app.crud.user import CRUDUser
from app.core.supabase import supabase
from app.core.security import get_current_user
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["auth"])
crud_user = CRUDUser(supabase)


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(current_user: dict = Depends(get_current_user)):
    """
    Get current authenticated user info.
    Requires a valid Supabase access token as Bearer token.
    """
    try:
        # Try to find existing user in our users table by email
        user = await crud_user.get_by_email(current_user["email"])

        if not user:
            # User exists in Supabase Auth but not in our users table yet.
            # Return basic info from Supabase Auth
            return UserResponse(
                user_id=current_user["supabase_id"],
                email=current_user["email"],
                user_name=current_user.get("user_name", current_user["email"].split("@")[0]),
                full_name=current_user.get("full_name", ""),
                phone=None,
                loyalty_points=0,
            )

        return UserResponse(
            user_id=user["user_id"],
            email=user["email"],
            user_name=user["user_name"],
            full_name=user["full_name"],
            phone=user.get("phone"),
            loyalty_points=user.get("loyalty_points", 0),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get user error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred",
        )
