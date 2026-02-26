from fastapi import APIRouter, Depends, Query, UploadFile, File
from typing import List, Optional
import asyncio
import logging

from app.crud.user import CRUDUser
from app.core.supabase import supabase_admin
from app.core.security import get_current_user, get_admin_user, CurrentUser
from app.core.exceptions import NotFoundException, UnauthorizedException
from app.schemas.user import (
    UserProfile, UserUpdate,
    UserBookingsResponse, BookingSummary,
    UserPointsResponse, PointTransaction,
    AdminUserResponse, AdminUserUpdate,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/users", tags=["users"])
crud_user = CRUDUser(supabase_admin)


# ── Current user ─────────────────────────────────────────────────────────────

@router.get("/me", response_model=UserProfile)
async def get_me(current_user: CurrentUser = Depends(get_current_user)):
    """Get current user's profile with theatre rewards and admin status."""
    user = await crud_user.get_by_id(current_user.user_id)
    if not user:
        raise NotFoundException("User", current_user.user_id)
    return user


@router.patch("/me", response_model=UserProfile)
async def update_me(
    body: UserUpdate,
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    Update current user's profile.
    Maps first_name/last_name to the DB 'full_name' column.
    """
    data: dict = {}

    # Handle Name Mapping
    if body.first_name is not None or body.last_name is not None:
        current = await crud_user.get_by_id(current_user.user_id)
        existing = (current.get("full_name") or "") if current else ""
        parts = existing.split(" ", 1)

        # Determine values, falling back to existing DB state if one side is missing in request
        existing_first = parts[0] if len(parts) > 0 else ""
        existing_last = parts[1] if len(parts) > 1 else ""

        first = body.first_name if body.first_name is not None else existing_first
        last = body.last_name if body.last_name is not None else existing_last
        data["full_name"] = f"{first} {last}".strip()

    # Direct field updates
    if body.phone is not None:
        data["phone"] = body.phone

    if body.date_of_birth is not None:
        # Pydantic date serializes to ISO string for Supabase automatically
        data["date_of_birth"] = body.date_of_birth.isoformat()

    if not data:
        return await get_me(current_user)

    updated = await crud_user.update(current_user.user_id, data)
    if not updated:
        raise NotFoundException("User", current_user.user_id)
    return updated

@router.post("/me/student-verification")
async def submit_student_verification(
    student_id_image: UploadFile = File(...),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Submit student ID image for verification.
    Admin reviews manually and toggles student_id_verified via Admin API."""
    logger.info(
        f"Student verification submitted — user: {current_user.user_id}, "
        f"file: {student_id_image.filename}"
    )
    return {"message": "Verification submitted, pending review"}


@router.get("/me/bookings", response_model=UserBookingsResponse)
async def get_my_bookings(
    status: Optional[str] = Query(None, description="Filter: pending|confirmed|cancelled"),
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=50),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Get booking history for current user (paginated)."""
    offset = (page - 1) * limit

    def _fetch():
        query = (
            supabase_admin.from_("booking_details")
            .select("*")
            .eq("user_id", current_user.user_id)
            .order("created_at", desc=True)
            .range(offset, offset + limit - 1)
        )
        if status:
            query = query.eq("booking_status", status)
        return query.execute()

    try:
        res = await asyncio.to_thread(_fetch)
        rows = res.data or []
    except Exception as e:
        logger.error(f"Failed to fetch bookings for {current_user.user_id}: {e}")
        rows = []

    return UserBookingsResponse(
        bookings=[BookingSummary(**r) for r in rows],
        total=len(rows),
        page=page,
        limit=limit,
    )


@router.get("/me/points", response_model=UserPointsResponse)
async def get_my_points(current_user: CurrentUser = Depends(get_current_user)):
    """Get points balance and transaction history."""
    user = await crud_user.get_by_id(current_user.user_id)
    # Note: DB column is loyalty_points, mapped to reward_points in UserProfile
    current_points = int((user or {}).get("loyalty_points", 0))

    try:
        res = await asyncio.to_thread(
            lambda: supabase_admin.table("membership_transactions")
                .select("id, points_delta, reason, created_at")
                .eq("user_id", current_user.user_id)
                .order("created_at", desc=True)
                .limit(50)
                .execute()
        )
        txns = [PointTransaction(**t) for t in (res.data or [])]
    except Exception as e:
        logger.error(f"Points fetch error: {e}")
        txns = []

    return UserPointsResponse(current_points=current_points, transactions=txns)

# ── Admin: manage all users ───────────────────────────────────────────────────
# Admin endpoints moved to /api/v1/admin/users in app/routes/admin.py

@router.get("/{user_id}", response_model=AdminUserResponse)
async def get_user(
    user_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Get user by ID. Admins can fetch anyone; users only fetch themselves."""
    if not current_user.is_admin and user_id != current_user.user_id:
        raise UnauthorizedException()
    user = await crud_user.get_by_id(user_id)
    if not user:
        raise NotFoundException("User", user_id)
    return user

# Admin PATCH moved to /api/v1/admin/users/{user_id} in app/routes/admin.py

@router.delete("/{user_id}")
async def deactivate_user(
    user_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Deactivate user account. Admins can deactivate anyone; users deactivate themselves."""
    if not current_user.is_admin and user_id != current_user.user_id:
        raise UnauthorizedException()
    success = await crud_user.deactivate(user_id)
    if not success:
        raise NotFoundException("User", user_id)
    return {"message": "User deactivated successfully"}
