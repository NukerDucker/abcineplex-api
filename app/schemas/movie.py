from pydantic import BaseModel
from datetime import date, datetime
from typing import List, Optional, Any


# ── Admin CRUD schemas (keep DB field names for inserts/updates) ──────────────

class MovieCreate(BaseModel):
    title: str
    release_date: date
    imdb_score: Optional[float] = None
    content_rating: str
    runtime_minutes: int                    # TMDB film runtime (excluding credits)
    duration_minutes: int                   # runtime_minutes + credits_duration_minutes (used for showtime end_time)
    director: Optional[str] = None
    starring: Optional[List[str]] = []      # written to movie_cast table
    synopsis: Optional[str] = None
    poster_url: Optional[str] = None
    banner_url: Optional[str] = None
    trailer_url: Optional[str] = None
    audio_languages: Optional[List[str]] = []      # written to movie_audio_languages table
    subtitle_languages: Optional[List[str]] = []   # written to movie_subtitle_languages table
    tag_event: Optional[str] = None
    release_status: str = "upcoming"
    genre: Optional[List[str]] = []         # written to movie_genres table
    credits_duration_minutes: int
    is_active: bool = True


class MovieUpdate(BaseModel):
    """All optional for partial updates (PATCH semantics)."""
    title: Optional[str] = None
    release_date: Optional[date] = None
    imdb_score: Optional[float] = None
    runtime_minutes: Optional[int] = None   # TMDB film runtime (excluding credits)
    duration_minutes: Optional[int] = None  # runtime_minutes + credits — recalculate if either changes
    content_rating: Optional[str] = None
    director: Optional[str] = None
    starring: Optional[List[str]] = None           # updates movie_cast table
    synopsis: Optional[str] = None
    poster_url: Optional[str] = None
    banner_url: Optional[str] = None
    trailer_url: Optional[str] = None
    audio_languages: Optional[List[str]] = None    # updates movie_audio_languages table
    subtitle_languages: Optional[List[str]] = None # updates movie_subtitle_languages table
    tag_event: Optional[str] = None
    release_status: Optional[str] = None
    genre: Optional[List[str]] = None              # updates movie_genres table
    is_active: Optional[bool] = None


# ── Spec-aligned public response schemas ──────────────────────────────────────
# NOTE: starring, genre, audio_languages, subtitle_languages are stored in
# separate join tables (movie_cast, movie_genres, movie_audio_languages,
# movie_subtitle_languages). CRUDMovie._assemble() flattens them back before
# returning — callers receive the same flat field names as before.

class MovieSummary(BaseModel):
    """Lightweight row for GET /movies list."""
    id: int
    title: str
    genre: Optional[List[str]] = None       # assembled from movie_genres join
    runtime_minutes: int = 0
    rating_tmdb: Optional[float] = None
    starring: Optional[List[str]] = None    # assembled from movie_cast join
    poster_url: Optional[str] = None
    banner_url: Optional[str] = None
    release_date: Optional[date] = None
    content_rating: Optional[str] = None
    audio_languages: Optional[List[str]] = None    # assembled from movie_audio_languages join
    subtitle_languages: Optional[List[str]] = None # assembled from movie_subtitle_languages join
    release_status: Optional[str] = None
    is_active: bool = True
    consensus_score: Optional[float] = None
    total_bookings: Optional[int] = None

    class Config:
        from_attributes = True


class MovieDetail(BaseModel):
    """Full detail for GET /movies/:id."""
    id: int
    title: str
    synopsis: Optional[str] = None
    genre: Optional[List[str]] = None       # assembled from movie_genres join
    runtime_minutes: int = 0               # TMDB film runtime (excluding credits)
    duration_minutes: int = 0              # runtime_minutes + credits (used for end_time display)
    trailer_url: Optional[str] = None
    poster_url: Optional[str] = None
    banner_url: Optional[str] = None
    starring: Optional[List[str]] = None    # assembled from movie_cast join
    director: Optional[str] = None
    release_date: Optional[date] = None
    imdb_score: Optional[float] = None
    rating_count: Optional[int] = None
    content_rating: Optional[str] = None
    audio_languages: Optional[List[str]] = None    # assembled from movie_audio_languages join
    subtitle_languages: Optional[List[str]] = None # assembled from movie_subtitle_languages join
    credits_duration_minutes: int = 5
    release_status: Optional[str] = None
    is_active: bool = True
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    consensus_score: Optional[float] = None
    total_bookings: Optional[int] = None

    class Config:
        from_attributes = True


class MovieListResponse(BaseModel):
    movies: List[MovieSummary]
    total: int
    page: int


# ── Showtime card shown inside GET /movies/:id/showtimes ─────────────────────

class ShowtimeCard(BaseModel):
    showtime_id: int
    theatre_name: Optional[str] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    language: Optional[str] = None
    available_seats: Optional[int] = None
    total_seats: Optional[int] = None
    base_price: float = 0.0
    student_discount_baht: Optional[float] = None
    member_discount_baht: Optional[float] = None
    total_time_commitment_minutes: int
    risk_adjusted_quality_score: float
    demand_badge: Optional[str] = None           # selling_fast | filling_up | available | plenty_of_space
    badge_label: Optional[str] = None            # Display string, None when badge is "available"
    seats_remaining_percent: Optional[float] = None


class MovieShowtimesResponse(BaseModel):
    movie_id: int
    showtimes_by_date: dict[str, List[ShowtimeCard]]
    furthest_available_date: Optional[str] = None


# Kept for backward compat with admin movie routes
class Movie(MovieDetail):
    pass


# ── Unique Feature Schemas ────────────────────────────────────────────────────

class RAQSBreakdown(BaseModel):
    base_rating: float
    confidence_weight: float
    recency_factor: float
    formula: str = "base_rating * confidence_weight * recency_factor"


class QualityScoreResponse(BaseModel):
    movie_id: int
    title: str
    rating_tmdb: float
    rating_count: int
    risk_adjusted_quality_score: float
    score_breakdown: RAQSBreakdown


# ── Consensus Score schemas ───────────────────────────────────────────────────

class ConsensusScoreBreakdown(BaseModel):
    avg_user_rating: float
    avg_user_rating_normalized: float
    total_bookings: int
    total_bookings_normalized: float
    weight_rating: float
    weight_bookings: float
    formula: str = "(avg_user_rating_normalized × 0.6) + (total_bookings_normalized × 0.4)"


class ConsensusScoreResponse(BaseModel):
    movie_id: int
    title: str
    consensus_score: float
    score_breakdown: ConsensusScoreBreakdown
    last_updated: Optional[str] = None


# ── Consensus / Top Picks schemas ─────────────────────────────────────────────

class TopPicksItem(BaseModel):
    id: int
    title: str
    banner_url: Optional[str] = None
    genre: Optional[List[str]] = None
    consensus_score: Optional[float] = None
    total_bookings: Optional[int] = None
    release_status: Optional[str] = None

    class Config:
        from_attributes = True


class TopPicksResponse(BaseModel):
    top_picks: List[TopPicksItem]
    total: int