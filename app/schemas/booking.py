from pydantic import BaseModel, Field, model_validator
from datetime import datetime
from typing import Any, List, Optional
from enum import Enum


class BookingStatus(str, Enum):
    PENDING   = "pending"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"
    CHANGED   = "changed"


# ── Guest booking schemas ─────────────────────────────────────

class GuestBookingRequest(BaseModel):
    """Used by POST /bookings/guest — no auth required."""
    showtime_id:    int
    seat_ids:       List[int] = Field(..., min_length=1, max_length=8)
    price_per_seat: float
    ticket_type:    str = "normal"
    email:          Optional[str] = None
    phone:          Optional[str] = None

    @model_validator(mode="after")
    def require_contact(self) -> "GuestBookingRequest":
        if not self.email and not self.phone:
            raise ValueError("Guest bookings require at least an email or phone number.")
        return self


class GuestBookingResponse(BaseModel):
    booking_id:       str
    guest_token:      str
    total_amount:     float
    payment_deadline: Optional[datetime] = None
    message:          str = "Guest booking created. Use the token to access your booking."


# ── Request schemas ───────────────────────────────────────────

class ReserveSeatRequest(BaseModel):
    """Sent when the user proceeds from seat selection to payment."""
    showtime_id:     int
    seat_ids:        List[int] = Field(..., min_length=1, max_length=8)
    price_per_seat:  float
    # ticket_type is the per-request intent and is written to each tickets row.
    ticket_type:     str = "normal"   # "normal" | "student"


class ConfirmPaymentRequest(BaseModel):
    """Sent to finalize a booking after mock payment succeeds."""
    booking_id:        str
    payment_intent_id: Optional[str] = None


class CancelBookingRequest(BaseModel):
    booking_id: str


class ChangeShowtimeRequest(BaseModel):
    new_showtime_id: int
    new_seat_ids: List[int] = Field(
        default_factory=list,
        description="Optional new seat IDs; empty to keep current seats",
    )


class ChangeSeatRequest(BaseModel):
    new_seat_ids: List[int] = Field(..., min_length=1, max_length=8)


# ── Response schemas ──────────────────────────────────────────

class ReserveSeatResponse(BaseModel):
    success:           bool
    booking_id:        Optional[str]       = None
    payment_deadline:  Optional[datetime]  = None
    total_amount:      Optional[float]     = None
    error:             Optional[str]       = None
    unavailable_seats: Optional[List[int]] = None


class ConfirmPaymentResponse(BaseModel):
    success:    bool
    message:    str
    booking_id: Optional[str]        = None
    tickets:    Optional[List[dict]] = None


class CancelBookingResponse(BaseModel):
    success: bool
    message: str


# ── Individual ticket ─────────────────────────────────────────

class TicketDetail(BaseModel):
    """
    One physical ticket within a booking.
    ticket_type lives here (migrated from bookings.ticket_type) so that
    a single booking can contain a mix of normal and student tickets.
    """
    ticket_id:     Optional[int]   = None
    seat_id:       int
    row_label:     str
    seat_number:   int
    ticket_type:   str             = "normal"   # "normal" | "student"
    price_paid:    Optional[float] = None
    qr_code_slug:  Optional[str]   = None


# ── Booking detail (returned by GET /bookings/:id) ────────────

class BookingDetail(BaseModel):
    """Full booking info including seats and QR codes."""
    booking_id:       Any
    user_id:          Any
    booking_status:   str
    # ticket_type removed from booking level — use tickets[n].ticket_type instead.
    num_tickets:      Optional[int]            = None
    total_amount:     float
    payment_deadline: Optional[datetime]       = None
    created_at:       Optional[datetime]       = None
    updated_at:       Optional[datetime]       = None
    showtime_id:      int
    screen_name:      Optional[str]            = None
    seats:            Optional[List[dict]]     = None
    movie_title:      Optional[str]            = None
    poster_url:       Optional[str]            = None
    showtime_start:   Optional[Any]            = None
    qr_code_data:     Optional[str]            = None
    tickets:          Optional[List[TicketDetail]] = None

    model_config = {"from_attributes": True}


# ── Misc ──────────────────────────────────────────────────────

class ExpiryWorkerResponse(BaseModel):
    released_count: int
    booking_ids:    Optional[List[str]] = None
    timestamp:      datetime = Field(default_factory=datetime.now)


# ── Legacy screen schemas (used by /bookings/screens endpoints) ───────────────

class AvailableSeat(BaseModel):
    seat_id:     int
    row_label:   str
    seat_number: int
    status:      str


class ScreenInfo(BaseModel):
    theatre_id:  int
    name:        str
    total_seats: int