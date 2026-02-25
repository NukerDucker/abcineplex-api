from fastapi import APIRouter, Depends
from typing import List

from app.crud.user import CRUDUser
from app.core.supabase import supabase_admin
from app.core.security import get_current_user, get_admin_user, CurrentUser
from app.core.exceptions import NotFoundException, UnauthorizedException
from app.schemas.user import UserResponse, UserUpdate, AdminUserUpdate

router = APIRouter(prefix="/api/users", tags=["users"])
crud_user = CRUDUser(supabase_admin)

# ---------------------------------------------------------------------------
# Current user
# ---------------------------------------------------------------------------

@router.get("/me", response_model=UserResponse)
async def get_me(current_user: CurrentUser = Depends(get_current_user)):
    """Return the authenticated user's profile (data fetched by security layer)."""
    return {
        "user_id": current_user.user_id,
        "email": current_user.email,
        "user_name": current_user.user_name,
        "full_name": current_user.full_name,
        "loyalty_points": current_user.loyalty_points,
        "is_admin": current_user.is_admin,
        "is_active": True,
    }


@router.patch("/me", response_model=UserResponse)
async def update_me(
    body: UserUpdate,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Update the authenticated user's own profile (full_name, user_name, phone)."""
    data = body.model_dump(exclude_none=True)
    if not data:
        return await get_me(current_user)

    updated = await crud_user.update(current_user.user_id, data)
    if not updated:
        raise NotFoundException("User", current_user.user_id)
    return updated


# ---------------------------------------------------------------------------
# Admin: manage all users
# ---------------------------------------------------------------------------

@router.get("/", response_model=List[UserResponse])
async def list_users(
    skip: int = 0,
    limit: int = 20,
    _: CurrentUser = Depends(get_admin_user),
):
    """List all users (admin only)."""
    return await crud_user.get_multi(skip, limit)


@router.get("/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Get any user by ID. Admins can fetch anyone; users can only fetch themselves."""
    if not current_user.is_admin and user_id != current_user.user_id:
        raise UnauthorizedException()

    user = await crud_user.get_by_id(user_id)
    if not user:
        raise NotFoundException("User", user_id)
    return user


@router.patch("/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: str,
    body: AdminUserUpdate,
    _: CurrentUser = Depends(get_admin_user),
):
    """Update any user's fields (admin only)."""
    data = body.model_dump(exclude_none=True)
    if not data:
        user = await crud_user.get_by_id(user_id)
        if not user:
            raise NotFoundException("User", user_id)
        return user

    updated = await crud_user.update(user_id, data)
    if not updated:
        raise NotFoundException("User", user_id)
    return updated


@router.delete("/{user_id}")
async def deactivate_user(
    user_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Deactivate a user account. Admins can deactivate anyone; users can deactivate themselves."""
    if not current_user.is_admin and user_id != current_user.user_id:
        raise UnauthorizedException()

    success = await crud_user.deactivate(user_id)
    if not success:
        raise NotFoundException("User", user_id)
    return {"message": "User deactivated successfully"}
