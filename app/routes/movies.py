from fastapi import APIRouter, Query
from typing import Optional
from datetime import date, timedelta, datetime

from app.crud.movie import CRUDMovie
from app.schemas.movie import (
    MovieListResponse, MovieSummary, MovieDetail,
    MovieShowtimesResponse, ShowtimeCard,
    QualityScoreResponse, RAQSBreakdown,
)
from app.core.supabase import supabase_admin
from app.core.exceptions import NotFoundException
from app.core.calculations import calc_raqs, calc_ttc

router = APIRouter(prefix="/api/v1/movies", tags=["movies"])
crud_movie = CRUDMovie(supabase_admin)


def _build_showtime_card(
    st: dict,
    runtime: int,
    credits_min: int,
    ttc: int,
    raqs: float,
) -> ShowtimeCard:
    """Build a ShowtimeCard from a raw showtime DB row."""
    raw_start = st.get("start_time", "")
    start_time_str = raw_start[11:16] if len(raw_start) >= 16 else None

    end_time_str = None
    if raw_start and runtime:
        try:
            st_dt = datetime.fromisoformat(raw_start.replace("Z", "+00:00"))
            end_dt = st_dt + timedelta(minutes=runtime + credits_min)
            end_time_str = end_dt.strftime("%H:%M")
        except ValueError:
            pass

    theatre_id = st.get("theatre_id")
    return ShowtimeCard(
        showtime_id=st["id"],
        theatre_name=f"Theatre {theatre_id}" if theatre_id else None,
        start_time=start_time_str,
        end_time=end_time_str,
        format=st.get("format"),
        language=st.get("language"),
        available_seats=st.get("available_seats"),
        total_seats=st.get("total_seats"),
        ticket_price_normal=st.get("ticket_price_normal") or st.get("base_price"),
        ticket_price_student=st.get("ticket_price_student"),
        ticket_price_member=st.get("ticket_price_member"),
        total_time_commitment_minutes=ttc,
        risk_adjusted_quality_score=raqs,
    )


# ── Public endpoints ──────────────────────────────────────────────────────────

@router.get("", response_model=MovieListResponse)
async def list_movies(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    status: Optional[str] = Query(None, alias="release_status")
):
    """Browse movies with optional release_, genre, and title-search filters."""
    rows, total = await crud_movie.get_multi(
        page=page, limit=limit, release_status=status, active_only=True
    )
    return MovieListResponse(
        movies=rows,  # FastAPI/Pydantic will automatically convert these dicts to MovieSummary objects
        total=total,
        page=page
    )


@router.get("/{movie_id}", response_model=MovieDetail)
async def get_movie(movie_id: int):
    """Get full movie detail."""
    movie = await crud_movie.get_by_id(movie_id)
    if not movie:
        raise NotFoundException("Movie", str(movie_id))
    return movie


@router.get("/{movie_id}/showtimes", response_model=MovieShowtimesResponse)
async def get_movie_showtimes(
    movie_id: int,
    date_from: Optional[date] = Query(
        None, alias="date", description="Start date YYYY-MM-DD (default: today)"
    ),
    days: int = Query(7, ge=1, le=30, description="Number of days to include"),
):
    """Get showtimes for a movie grouped by date, each with TTC and RAQS."""
    movie = await crud_movie.get_by_id(movie_id)
    if not movie:
        raise NotFoundException("Movie", str(movie_id))

    start = date_from or date.today()
    end = start + timedelta(days=days - 1)

    raw = await crud_movie.get_showtimes_for_movie(
        movie_id=movie_id,
        from_date=start.isoformat(),
        to_date=f"{end.isoformat()}T23:59:59",
    )

    # RAQS is per-movie (same for every showtime card)
    rating = float(movie.get("imdb_score") or 0)
    votes = int(movie.get("rating_count") or 0)
    rel_raw = movie.get("release_date")
    rel_date = date.fromisoformat(rel_raw) if isinstance(rel_raw, str) else rel_raw
    raqs = calc_raqs(rating, votes, rel_date)

    runtime = int(movie.get("duration_minutes") or 0)
    credits_min = int(movie.get("credits_duration_minutes") or 5)
    ttc = calc_ttc(runtime, credits_min)

    by_date: dict[str, list[ShowtimeCard]] = {}
    furthest: Optional[str] = None

    for st in raw:
        raw_start = st.get("start_time", "")
        day_key = raw_start[:10] if raw_start else "unknown"
        card = _build_showtime_card(st, runtime, credits_min, ttc, raqs)
        by_date.setdefault(day_key, []).append(card)
        furthest = day_key

    return MovieShowtimesResponse(
        movie_id=movie_id,
        showtimes_by_date=by_date,
        furthest_available_date=furthest,
    )


@router.get("/{movie_id}/quality-score", response_model=QualityScoreResponse)
async def get_movie_quality_score(movie_id: int):
    """Get the Risk-Adjusted Quality Score for a movie with breakdown."""
    movie = await crud_movie.get_by_id(movie_id)
    if not movie:
        raise NotFoundException("Movie", str(movie_id))

    # Extract RAQS components
    rating = float(movie.get("imdb_score") or 0)
    votes = int(movie.get("rating_count") or 0)
    rel_raw = movie.get("release_date")
    rel_date = date.fromisoformat(rel_raw) if isinstance(rel_raw, str) else rel_raw

    # Calculate RAQS
    raqs = calc_raqs(rating, votes, rel_date)

    # Build confidence and recency factors for breakdown
    confidence = votes / (votes + 1500) if votes > 0 else 0.0
    recency = 1.0
    if rel_date:
        today = date.today()
        months_old = (today.year - rel_date.year) * 12 + (today.month - rel_date.month)
        if months_old > 18:
            recency = 0.90
        elif months_old > 6:
            recency = 0.95

    return QualityScoreResponse(
        movie_id=movie_id,
        title=movie.get("title", ""),
        rating_tmdb=rating,
        rating_count=votes,
        risk_adjusted_quality_score=raqs,
        score_breakdown=RAQSBreakdown(
            base_rating=rating,
            confidence_weight=round(confidence, 4),
            recency_factor=recency,
        ),
    )


# ── Admin endpoints ───────────────────────────────────────────────────────────
# Moved to /api/v1/admin/movies in app/routes/admin.py
