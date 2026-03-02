from pydantic import BaseModel, model_validator, Field, ConfigDict
from typing import Optional, List, Any
from datetime import date, datetime

class UserProfile(BaseModel):
    """
    Spec-aligned user profile response.
    Includes is_admin to allow frontend role-based UI rendering.
    """
    id: str
    email: str
    user_name: str
    full_name: str
    is_admin: bool = False
    phone: Optional[str] = None
    date_of_birth: Optional[date] = None
    is_student: bool = False
    student_id_verified: bool = False
    membership_tier: str = "free"
    reward_points: int = 0
    attendance_streak: int = 0
    has_password: bool = True  # False for OAuth users who haven't set a password yet

    @model_validator(mode="before")
    @classmethod
    def _map_db_fields(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data

        out = dict(data)

        # 1. Map ID (user_id -> id)
        out.setdefault("id", data.get("user_id", ""))

        # 2. Normalize full_name
        full_name = (data.get("full_name") or "").strip()

        # 3. user_name fallback — Google OAuth users won't have one until they update it
        if not data.get("user_name"):
            email = data.get("email", "")
            out["user_name"] = email if email else "user"

        # 4. Map Points (loyalty_points -> reward_points)
        out.setdefault("reward_points", data.get("loyalty_points", 0))

        # 4b. Map streak from DB column
        out.setdefault("attendance_streak", data.get("attendance_streak", 0))

        # 5. Map Admin Status (explicitly ensure it's captured from DB)
        out.setdefault("is_admin", data.get("is_admin", False))

        # 6. has_password: True if password_hash column is set
        raw_hash = data.get("password_hash")
        out["has_password"] = bool(raw_hash)

        return out

    model_config = ConfigDict(from_attributes=True)


class UserUpdate(BaseModel):
    """
    Fields a user can update on their own profile.
    NOTE: is_admin is EXCLUDED here for security.
    """
    full_name: Optional[str] = None
    phone: Optional[str] = None
    date_of_birth: Optional[date] = None


class BookingSummary(BaseModel):
    """Lightweight booking row for the /users/me/bookings list."""
    booking_id: Any
    showtime_id: Optional[int] = None
    booking_status: Optional[str] = None
    total_amount: Optional[float] = None
    created_at: Optional[datetime] = None
    movie_title: Optional[str] = None
    poster_url: Optional[str] = None
    screen_name: Optional[str] = None
    showtime_start: Optional[str] = None
    seats: Optional[List[str]] = None

    model_config = ConfigDict(from_attributes=True)


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

    model_config = ConfigDict(from_attributes=True)


class UserPointsResponse(BaseModel):
    current_points: int
    transactions: List[PointTransaction]


# ── Admin schemas ──────────────────────────────────────────────────────────────

class AdminUserResponse(BaseModel):
    """Full user row for admin management — uses raw DB field names."""
    id: str
    email: str
    user_name: Optional[str] = None
    full_name: Optional[str] = None
    phone: Optional[str] = None
    loyalty_points: int = 0
    is_admin: bool = False
    is_active: bool = True
    is_student: bool = False
    student_id_verified: bool = False
    membership_tier: str = "free"  # Not in DB; kept for frontend compat
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class AdminUserUpdate(BaseModel):
    """Fields only an admin can update on any user record via Admin Panel."""
    full_name: Optional[str] = None
    phone: Optional[str] = None
    loyalty_points: Optional[int] = None
    is_admin: Optional[bool] = None
    is_active: Optional[bool] = None
    is_student: Optional[bool] = None
    student_id_verified: Optional[bool] = None