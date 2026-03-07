from fastapi import APIRouter, Query
from typing import Optional
from datetime import date, timedelta, datetime

from app.crud.movie import CRUDMovie
from app.crud.showtime import CRUDShowtime
from app.schemas.movie import (
    MovieListResponse, MovieSummary, MovieDetail,
    MovieShowtimesResponse, ShowtimeCard,
    QualityScoreResponse, RAQSBreakdown,
    ConsensusScoreResponse, ConsensusScoreBreakdown,
    TopPicksItem, TopPicksResponse,
)
from app.core.supabase import supabase_admin
from app.core.exceptions import NotFoundException
from app.core.calculations import calc_raqs, calc_ttc, calc_demand_badge

router = APIRouter(prefix="/api/v1/movies", tags=["movies"])
crude_movie = CRUDMovie(supabase_admin)
crude_showtime = CRUDShowtime(supabase_admin)

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
    theatre_row = st.get("theatres") or {}
    theatre_name = theatre_row.get("name") if isinstance(theatre_row, dict) else None
    if not theatre_name and theatre_id:
        theatre_name = f"Theatre {theatre_id}"
    available = st.get("available_seats") or 0
    total = st.get("total_seats") or 0
    badge_data = calc_demand_badge(available, total)
    return ShowtimeCard(
        showtime_id=st["id"],
        theatre_name=theatre_name,
        start_time=start_time_str,
        end_time=end_time_str,
        language=st.get("language"),
        available_seats=st.get("available_seats"),
        total_seats=st.get("total_seats"),
        base_price=st.get("base_price") or 0.0,
        student_discount_baht=st.get("student_discount_baht"),
        member_discount_baht=st.get("member_discount_baht"),
        total_time_commitment_minutes=ttc,
        risk_adjusted_quality_score=raqs,
        **badge_data,
    )


# ── Public endpoints ──────────────────────────────────────────────────────────

@router.get("", response_model=MovieListResponse)
async def list_movies(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    status: Optional[str] = Query(None, alias="release_status")
):
    """Browse movies with optional release_, genre, and title-search filters."""
    rows, total = await crude_movie.get_multi(
        page=page, limit=limit, release_status=status, active_only=True
    )
    return MovieListResponse(
        movies=rows,  # FastAPI/Pydantic will automatically convert these dicts to MovieSummary objects
        total=total,
        page=page
    )


@router.get("/top-picks", response_model=TopPicksResponse)
async def get_top_picks(
    limit: int = Query(10, ge=1, le=50),
):
    """Return top movies ranked by Consensus AI score."""
    movies = await crude_movie.get_top_picks(limit=limit)
    return TopPicksResponse(top_picks=movies, total=len(movies))


@router.get("/{movie_id}", response_model=MovieDetail)
async def get_movie(movie_id: int):
    """Get full movie detail."""
    movie = await crude_movie.get_by_id(movie_id)
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
    active: Optional[bool] = Query(True, description="Filter by active status (true = active only, false = inactive only, null = all)"),
):
    """Get showtimes for a movie grouped by date, each with TTC and RAQS.

    Query Parameters:
        active: true (active only - default), false (inactive only), null (all showtimes)
    """
    movie = await crude_movie.get_by_id(movie_id)
    if not movie:
        raise NotFoundException("Movie", str(movie_id))

    start = date_from or date.today()
    end = start + timedelta(days=days - 1)

    # Use optimized CRUD method that filters at database level
    # Default to active=True to hide inactive showtimes from customers
    raw = await crude_showtime.get_showtimes_by_movie_and_date(
        movie_id=movie_id,
        from_date=start.isoformat(),
        to_date=f"{end.isoformat()}T23:59:59",
        is_active=active,
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
        # Only advance furthest_available_date when this showtime has at least 1 seat free
        if (st.get("available_seats") or 0) > 0:
            furthest = day_key

    return MovieShowtimesResponse(
        movie_id=movie_id,
        showtimes_by_date=by_date,
        furthest_available_date=furthest,
    )


@router.get("/{movie_id}/quality-score", response_model=QualityScoreResponse)
async def get_movie_quality_score(movie_id: int):
    """Get the Risk-Adjusted Quality Score for a movie with breakdown."""
    movie = await crude_movie.get_by_id(movie_id)
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


@router.get("/{movie_id}/consensus-score", response_model=ConsensusScoreResponse)
async def get_movie_consensus_score(movie_id: int):
    """Get the full Consensus Score breakdown for a movie."""
    from app.core.supabase import supabase_admin as _sa
    import asyncio as _asyncio

    movie = await crude_movie.get_by_id(movie_id)
    if not movie:
        raise NotFoundException("Movie", str(movie_id))

    # Aggregate avg rating from movie_reviews
    rating_res = await _asyncio.to_thread(
        lambda: _sa.table("movie_reviews")
            .select("rating")
            .eq("movie_id", movie_id)
            .execute()
    )
    ratings = [r["rating"] for r in (rating_res.data or []) if r.get("rating") is not None]
    avg_rating = round(sum(ratings) / len(ratings), 2) if ratings else 0.0

    # Count confirmed bookings for this movie's showtimes
    showtime_res = await _asyncio.to_thread(
        lambda: _sa.table("showtimes")
            .select("id")
            .eq("movie_id", movie_id)
            .execute()
    )
    showtime_ids = [s["id"] for s in (showtime_res.data or [])]
    total_bookings = 0
    if showtime_ids:
        bk_res = await _asyncio.to_thread(
            lambda: _sa.table("bookings")
                .select("id", count="exact")
                .in_("showtime_id", showtime_ids)
                .eq("booking_status", "confirmed")
                .execute()
        )
        total_bookings = bk_res.count or 0

    bookings_scale = 2000
    weight_rating = 0.6
    weight_bookings = 0.4
    rating_norm = round((avg_rating / 5.0) * 100, 2)
    bookings_norm = round(min((total_bookings / bookings_scale) * 100, 100), 2)
    score = round((rating_norm * weight_rating) + (bookings_norm * weight_bookings), 2)

    return ConsensusScoreResponse(
        movie_id=movie_id,
        title=movie.get("title", ""),
        consensus_score=score,
        score_breakdown=ConsensusScoreBreakdown(
            avg_user_rating=avg_rating,
            avg_user_rating_normalized=rating_norm,
            total_bookings=total_bookings,
            total_bookings_normalized=bookings_norm,
            weight_rating=weight_rating,
            weight_bookings=weight_bookings,
        ),
        last_updated=movie.get("consensus_score_updated_at"),
    )


@router.get("/bulk/all-active-showtimes")
async def get_all_active_showtimes(
    active: Optional[bool] = Query(True, description="Filter by active status (true = active only, false = inactive only, null = all)"),
):
    """Get ALL showtimes for bulk fetch (mobile/frontend filtering).
    Returns active showtimes by default - frontend filters by movie_id, date range, etc.

    Query Parameters:
        active: true (active only - default), false (inactive only), null (all showtimes)
    """
    showtimes = await crude_showtime.get_all_active_showtimes(is_active=active)
    return {"showtimes": showtimes, "total": len(showtimes)}


# ── Admin endpoints ───────────────────────────────────────────────────────────
# Moved to /api/v1/admin/movies in app/routes/admin.py
