from pydantic import BaseModel, Field
from datetime import datetime
from typing import Any, List, Optional
from enum import Enum


class BookingStatus(str, Enum):
    PENDING   = "pending"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"
    CHANGED   = "changed"


# ── Request schemas ───────────────────────────────────────────

class ReserveSeatRequest(BaseModel):
    """Sent when the user proceeds from seat selection to payment."""
    showtime_id:     int
    seat_ids:        List[int] = Field(..., min_length=1, max_length=8)
    price_per_seat:  float
    ticket_type:     str = "normal"   # "normal" | "student"


class ConfirmPaymentRequest(BaseModel):
    """Sent to finalize a booking after mock payment succeeds."""
    booking_id:       str             # UUID string
    payment_intent_id: Optional[str] = None


class CancelBookingRequest(BaseModel):
    booking_id: str                   # UUID string


class ChangeShowtimeRequest(BaseModel):
    new_showtime_id: int
    new_seat_ids: List[int] = Field(default_factory=list, description="Optional new seat IDs; empty to keep current seats")


# ── Response schemas ──────────────────────────────────────────

class ReserveSeatResponse(BaseModel):
    success:          bool
    booking_id:       Optional[str]   = None   # UUID
    payment_deadline: Optional[datetime] = None
    total_amount:     Optional[float] = None
    error:            Optional[str]   = None
    unavailable_seats: Optional[List[int]] = None


class ConfirmPaymentResponse(BaseModel):
    success:    bool
    message:    str
    booking_id: Optional[str]        = None
    tickets:    Optional[List[dict]] = None


class CancelBookingResponse(BaseModel):
    success: bool
    message: str


# ── Booking detail (returned by GET /bookings/:id) ────────────

class BookingDetail(BaseModel):
    """Full booking info including seats and QR codes."""
    booking_id:       Any             # UUID — using Any so Pydantic accepts both str and UUID
    user_id:          Any             # UUID
    booking_status:   str
    ticket_type:      Optional[str]   = None
    num_tickets:      Optional[int]   = None
    total_amount:     float
    payment_deadline: Optional[datetime] = None
    created_at:       Optional[datetime] = None
    updated_at:       Optional[datetime] = None
    showtime_id:      int
    screen_name:      Optional[str]   = None
    seats:            Optional[List[dict]] = None   # [{"seat_id": 1, "row_label": "A", "seat_number": 1}, ...]
    movie_title:      Optional[str]   = None
    poster_url:       Optional[str]   = None
    showtime_start:   Optional[Any]   = None
    qr_code_data:     Optional[str]   = None
    tickets:          Optional[List[dict]] = None

    model_config = {"from_attributes": True}


# ── Misc ──────────────────────────────────────────────────────

class ExpiryWorkerResponse(BaseModel):
    released_count: int
    booking_ids:    Optional[List[str]] = None
    timestamp:      datetime = Field(default_factory=datetime.now)


# ── Legacy screen schemas (used by /bookings/screens endpoints) ─

class AvailableSeat(BaseModel):
    seat_id:     int
    row_label:   str
    seat_number: int
    status:      str


class ScreenInfo(BaseModel):
    theatre_id:  int
    name:        str
    total_seats: int
