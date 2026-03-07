from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, List


# ── Admin CRUD schemas (keep existing DB field names) ─────────────────────────

class ShowtimeCreate(BaseModel):
    movie_id: int
    theatre_id: int = Field(..., description="Screen/theatre ID")
    start_time: datetime
    base_price: float = Field(..., ge=0)
    audio_language: Optional[str] = None
    subtitle_language: Optional[str] = None
    student_discount_baht: Optional[float] = Field(None, ge=0)
    member_discount_baht: Optional[float] = Field(None, ge=0)


class ShowtimeUpdate(BaseModel):
    movie_id: Optional[int] = None
    theatre_id: Optional[int] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    base_price: Optional[float] = Field(None, ge=0)
    audio_language: Optional[str] = None
    subtitle_language: Optional[str] = None
    language: Optional[str] = None
    student_discount_baht: Optional[float] = Field(None, ge=0)
    member_discount_baht: Optional[float] = Field(None, ge=0)


class Showtime(BaseModel):
    """Raw DB row — used by admin endpoints."""
    id: int
    movie_id: int
    theatre_id: int
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    base_price: float = 0.0
    audio_language: Optional[str] = None
    subtitle_language: Optional[str] = None
    language: Optional[str] = None
    student_discount_baht: Optional[float] = None
    member_discount_baht: Optional[float] = None
    is_active: Optional[bool] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

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


class PricingInfo(BaseModel):
    base_price: float = 0.0
    student_discount_baht: Optional[float] = None
    member_discount_baht: Optional[float] = None


class TicketPrices(BaseModel):
    normal: float
    student: Optional[float] = None


class ShowtimeDetail(BaseModel):
    """Full showtime detail per spec § 5.4."""
    id: int
    movie: Optional[MovieRef] = None
    theatre: Optional[TheatreRef] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    estimated_end_with_credits: Optional[datetime] = None
    language: Optional[str] = None
    available_seats: Optional[int] = None
    total_seats: Optional[int] = None
    base_price: float = 0.0
    student_discount_baht: Optional[float] = None
    member_discount_baht: Optional[float] = None
    ticket_prices: Optional[TicketPrices] = None
    total_time_commitment_minutes: int = 0
    risk_adjusted_quality_score: float = 0.0
    demand_badge: Optional[str] = None           # selling_fast | filling_up | available | plenty_of_space
    badge_label: Optional[str] = None            # Display string, None when badge is "available"
    seats_remaining_percent: Optional[float] = None


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


# ── Unique Feature Schemas ───────────────────────────────────────────────────────

class TTCComponents(BaseModel):
    """Total Time Commitment component breakdown."""
    travel_to_theatre_minutes: int
    pre_show_ads_minutes: int
    runtime_minutes: int
    credits_minutes: int
    travel_from_theatre_minutes: int


class TimeCommitmentResponse(BaseModel):
    """Time commitment response with TTC breakdown per spec § 5.12."""
    showtime_id: int
    movie_title: str
    components: TTCComponents
    total_time_commitment_minutes: int
    show_start: datetime
    movie_end_time: datetime
    credits_end_time: datetime
    estimated_home_arrival: datetime
