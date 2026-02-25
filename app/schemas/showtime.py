from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, List


# ── Admin CRUD schemas (keep existing DB field names) ─────────────────────────

class ShowtimeCreate(BaseModel):
    movie_id: int
    screen_id: int = Field(..., description="Screen/theatre ID")
    start_time: datetime
    base_price: float = Field(..., ge=0)
    # Extended spec fields (optional — only stored if DB column exists)
    language: Optional[str] = None
    format: Optional[str] = None
    ticket_price_normal: Optional[float] = None
    ticket_price_student: Optional[float] = None
    ticket_price_member: Optional[float] = None


class ShowtimeUpdate(BaseModel):
    movie_id: Optional[int] = None
    screen_id: Optional[int] = None
    start_time: Optional[datetime] = None
    base_price: Optional[float] = Field(None, ge=0)
    language: Optional[str] = None
    format: Optional[str] = None
    ticket_price_normal: Optional[float] = None
    ticket_price_student: Optional[float] = None
    ticket_price_member: Optional[float] = None


class Showtime(BaseModel):
    """Raw DB row — used by admin endpoints."""
    id: int
    movie_id: int
    screen_id: int
    start_time: Optional[datetime] = None
    base_price: float = 0.0
    language: Optional[str] = None
    format: Optional[str] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# ── Spec-aligned public response schemas ──────────────────────────────────────

class MovieRef(BaseModel):
    id: int
    title: str
    runtime_minutes: int = 0


class TheatreRef(BaseModel):
    id: int
    name: str


class TicketPrices(BaseModel):
    normal: Optional[float] = None
    student: Optional[float] = None
    member: Optional[float] = None


class ShowtimeDetail(BaseModel):
    """Full showtime detail per spec § 5.4."""
    id: int
    movie: Optional[MovieRef] = None
    theatre: Optional[TheatreRef] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    estimated_end_with_credits: Optional[datetime] = None
    format: Optional[str] = None
    language: Optional[str] = None
    available_seats: Optional[int] = None
    total_seats: Optional[int] = None
    ticket_prices: TicketPrices = Field(default_factory=TicketPrices)
    total_time_commitment_minutes: int = 0
    risk_adjusted_quality_score: float = 0.0


# ── Seat map schemas ──────────────────────────────────────────────────────────

# DB status → spec status
_STATUS_MAP = {
    "available": "available",
    "reserved": "held",
    "sold": "booked",
    "maintenance": "disabled",
}


class SeatInMap(BaseModel):
    seat_id: int
    row_label: str
    seat_number: int
    seat_type: str = "standard"
    status: str  # available | held | booked | disabled


class SeatLayout(BaseModel):
    rows: List[str]
    seats_per_row: int


class SeatMapResponse(BaseModel):
    """Seat map for GET /showtimes/:id/seats."""
    showtime_id: int
    theatre_id: Optional[int] = None
    layout: SeatLayout
    seats: List[SeatInMap]
