from pydantic import BaseModel, model_validator
from typing import Optional, List, Any
from datetime import date, datetime


class UserProfile(BaseModel):
    """Spec-aligned user profile response.
    Accepts DB rows (full_name / loyalty_points) and maps them to spec fields."""

    id: str
    email: str
    first_name: str
    last_name: str
    phone: Optional[str] = None
    date_of_birth: Optional[date] = None
    is_student: bool = False
    student_id_verified: bool = False
    membership_tier: str = "free"
    reward_points: int = 0
    attendance_streak: int = 0

    @model_validator(mode="before")
    @classmethod
    def _map_db_fields(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        out = dict(data)
        # id ← user_id
        out.setdefault("id", data.get("user_id", ""))
        # first_name / last_name ← full_name (split on first space)
        full_name = (data.get("full_name") or "").strip()
        parts = full_name.split(" ", 1)
        out.setdefault("first_name", parts[0])
        out.setdefault("last_name", parts[1] if len(parts) > 1 else "")
        # reward_points ← loyalty_points
        out.setdefault("reward_points", data.get("loyalty_points", 0))
        return out

    class Config:
        from_attributes = True


class UserUpdate(BaseModel):
    """Fields a user can update on their own profile."""
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    phone: Optional[str] = None


class BookingSummary(BaseModel):
    """Lightweight booking row for the /users/me/bookings list."""
    booking_id: Any
    showtime_id: Optional[int] = None
    booking_status: Optional[str] = None
    total_amount: Optional[float] = None
    created_at: Optional[datetime] = None
    movie_title: Optional[str] = None
    screen_name: Optional[str] = None
    showtime_start: Optional[str] = None
    seats: Optional[List[str]] = None

    class Config:
        from_attributes = True


class UserBookingsResponse(BaseModel):
    bookings: List[BookingSummary]
    total: int
    page: int
    limit: int


class PointTransaction(BaseModel):
    id: Any
    points_delta: int
    reason: str
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class UserPointsResponse(BaseModel):
    current_points: int
    transactions: List[PointTransaction]


# ── Admin schemas ──────────────────────────────────────────────────────────────

class AdminUserResponse(BaseModel):
    """Full user row for admin endpoints — uses raw DB field names."""
    user_id: str
    email: str
    user_name: Optional[str] = None
    full_name: Optional[str] = None
    phone: Optional[str] = None
    loyalty_points: int = 0
    is_admin: bool = False
    is_active: bool = True
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class AdminUserUpdate(BaseModel):
    """Fields admin can update on any user record."""
    full_name: Optional[str] = None
    phone: Optional[str] = None
    loyalty_points: Optional[int] = None
    is_admin: Optional[bool] = None
    is_active: Optional[bool] = None
    is_student: Optional[bool] = None
    student_id_verified: Optional[bool] = None
    membership_tier: Optional[str] = None
