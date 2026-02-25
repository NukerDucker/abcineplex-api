from pydantic import BaseModel, model_validator
from datetime import date, datetime
from typing import List, Optional, Any


# ── Admin CRUD schemas (keep DB field names for inserts/updates) ──────────────

class MovieCreate(BaseModel):
    title: str
    release_date: date
    imdb_score: Optional[float] = None
    duration_minutes: int
    content_rating: Optional[str] = None
    director: Optional[str] = None
    starring: Optional[List[str]] = []
    synopsis: Optional[str] = None
    poster_url: Optional[str] = None
    banner_url: Optional[str] = None
    trailer_url: Optional[str] = None
    audio_languages: Optional[List[str]] = []
    subtitle_languages: Optional[List[str]] = []
    tag_event: Optional[str] = None
    release_status: str = "upcoming"
    genres: Optional[List[str]] = []


class MovieUpdate(BaseModel):
    """All optional for partial updates (PATCH semantics)."""
    title: Optional[str] = None
    release_date: Optional[date] = None
    imdb_score: Optional[float] = None
    duration_minutes: Optional[int] = None
    content_rating: Optional[str] = None
    director: Optional[str] = None
    starring: Optional[List[str]] = None
    synopsis: Optional[str] = None
    poster_url: Optional[str] = None
    banner_url: Optional[str] = None
    trailer_url: Optional[str] = None
    audio_languages: Optional[List[str]] = None
    subtitle_languages: Optional[List[str]] = None
    tag_event: Optional[str] = None
    release_status: Optional[str] = None
    genres: Optional[List[str]] = None


# ── Spec-aligned public response schemas ──────────────────────────────────────

def _genre_str(genres: Any) -> Optional[str]:
    if isinstance(genres, list):
        return ", ".join(genres) if genres else None
    return genres or None


class MovieSummary(BaseModel):
    """Lightweight row for GET /movies list."""
    id: int
    title: str
    genre: Optional[str] = None
    runtime_minutes: int = 0
    rating_tmdb: Optional[float] = None
    poster_url: Optional[str] = None
    status: Optional[str] = None

    @model_validator(mode="before")
    @classmethod
    def _map(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        out = dict(data)
        out.setdefault("runtime_minutes", data.get("duration_minutes", 0))
        out.setdefault("rating_tmdb", data.get("imdb_score"))
        out.setdefault("status", data.get("release_status"))
        out.setdefault("genre", _genre_str(data.get("genres")))
        return out

    class Config:
        from_attributes = True


class MovieDetail(BaseModel):
    """Full detail for GET /movies/:id."""
    id: int
    title: str
    synopsis: Optional[str] = None
    genre: Optional[str] = None
    runtime_minutes: int = 0
    trailer_url: Optional[str] = None
    poster_url: Optional[str] = None
    banner_url: Optional[str] = None
    cast_json: Optional[Any] = None
    director: Optional[str] = None
    release_date: Optional[date] = None
    rating_tmdb: Optional[float] = None
    rating_count: Optional[int] = None
    credits_duration_minutes: int = 5
    status: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    @model_validator(mode="before")
    @classmethod
    def _map(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        out = dict(data)
        out.setdefault("runtime_minutes", data.get("duration_minutes", 0))
        out.setdefault("rating_tmdb", data.get("imdb_score"))
        out.setdefault("status", data.get("release_status"))
        out.setdefault("cast_json", data.get("starring", []))
        out.setdefault("genre", _genre_str(data.get("genres")))
        out.setdefault("credits_duration_minutes", 5)
        return out

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
    format: Optional[str] = None
    language: Optional[str] = None
    available_seats: Optional[int] = None
    total_seats: Optional[int] = None
    ticket_price_normal: Optional[float] = None
    ticket_price_student: Optional[float] = None
    ticket_price_member: Optional[float] = None
    total_time_commitment_minutes: int
    risk_adjusted_quality_score: float


class MovieShowtimesResponse(BaseModel):
    movie_id: int
    showtimes_by_date: dict[str, List[ShowtimeCard]]
    furthest_available_date: Optional[str] = None


# Kept for backward compat with admin movie routes
class Movie(MovieDetail):
    pass
