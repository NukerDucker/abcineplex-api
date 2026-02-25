from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, List

MAX_SEATS_PER_HOLD = 8  # business rule constant


# ── Seat info ─────────────────────────────────────────────────────────────────

class SeatBase(BaseModel):
    row_label: str = Field(..., description="Row label (e.g., A, B, C)")
    seat_number: int = Field(..., gt=0, description="Seat number")


class SeatDetail(SeatBase):
    """Detailed seat information"""
    seat_id: int
    status: str  # available, reserved, sold, maintenance
    screen_id: int
    price: Optional[float] = None


# ── Hold schemas (5.5) ────────────────────────────────────────────────────────

class HoldRequest(BaseModel):
    seat_ids: List[int] = Field(
        ...,
        min_length=1,
        max_length=MAX_SEATS_PER_HOLD,
        description="Seat IDs to place a 5-minute hold on",
    )


class HoldResponse(BaseModel):
    hold_id: str          # maps to booking_id (DB-backed hold, no Redis required)
    seat_ids: List[int]
    expires_at: datetime
    expires_in_seconds: int


class ReleaseHoldRequest(BaseModel):
    hold_id: str


class HoldStatusResponse(BaseModel):
    hold_id: str
    is_active: bool
    expires_in_seconds: int