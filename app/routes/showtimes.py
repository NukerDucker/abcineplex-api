from fastapi import APIRouter, Depends
from typing import List, Optional
from datetime import datetime, date, timedelta

from app.crud.showtime import CRUDShowtime
from app.schemas.showtime import (
    Showtime, ShowtimeCreate, ShowtimeUpdate,
    ShowtimeDetail, MovieRef, TheatreRef, TicketPrices,
    SeatMapResponse, SeatLayout, SeatInMap, _STATUS_MAP,
)
from app.core.supabase import supabase_admin
from app.core.exceptions import NotFoundException
from app.core.security import get_admin_user
from app.core.calculations import calc_raqs, calc_ttc

router = APIRouter(prefix="/api/v1/showtimes", tags=["showtimes"])
crud_showtime = CRUDShowtime(supabase_admin)


# ── Private helpers (reduce route cognitive complexity) ───────────────────────

def _parse_start_time(raw: Optional[str | datetime]) -> Optional[datetime]:
    if not raw:
        return None
    if isinstance(raw, str):
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    return raw


def _derive_times(
    start_dt: Optional[datetime], runtime: int, credits_min: int
) -> tuple[Optional[datetime], Optional[datetime]]:
    if not start_dt:
        return None, None
    end_dt = start_dt + timedelta(minutes=runtime)
    end_credits = end_dt + timedelta(minutes=credits_min)
    return end_dt, end_credits


def _movie_raqs_ttc(movie_row: dict) -> tuple[float, int]:
    rating = float(movie_row.get("imdb_score") or 0)
    votes = int(movie_row.get("rating_count") or 0)
    rel_raw = movie_row.get("release_date")
    rel_date = date.fromisoformat(rel_raw) if isinstance(rel_raw, str) else rel_raw
    runtime = int(movie_row.get("duration_minutes") or 0)
    credits_min = int(movie_row.get("credits_duration_minutes") or 5)
    return calc_raqs(rating, votes, rel_date), calc_ttc(runtime, credits_min)


# ── Public endpoints ──────────────────────────────────────────────────────────

@router.get("/{showtime_id}", response_model=ShowtimeDetail)
async def get_showtime(showtime_id: int):
    """Get full showtime detail including TTC and RAQS."""
    raw = await crud_showtime.get_detail(showtime_id)
    if not raw:
        raise NotFoundException("Showtime", str(showtime_id))

    movie_row = raw.get("movies") or {}
    screen_row = raw.get("screens") or {}
    runtime = int(movie_row.get("duration_minutes") or 0)
    credits_min = int(movie_row.get("credits_duration_minutes") or 5)

    start_dt = _parse_start_time(raw.get("start_time"))
    end_dt, end_credits_dt = _derive_times(start_dt, runtime, credits_min)
    raqs, ttc = _movie_raqs_ttc(movie_row)

    screen_id = raw.get("screen_id")
    available = None
    if screen_id:
        occupancy = await crud_showtime.get_screen_occupancy(screen_id)
        available = occupancy.get("available_seats")

    return ShowtimeDetail(
        id=raw["id"],
        movie=MovieRef(id=movie_row.get("id", 0), title=movie_row.get("title", ""), runtime_minutes=runtime) if movie_row else None,
        theatre=TheatreRef(id=screen_row.get("id", 0), name=screen_row.get("name", "")) if screen_row else None,
        start_time=start_dt,
        end_time=end_dt,
        estimated_end_with_credits=end_credits_dt,
        format=raw.get("format"),
        language=raw.get("language"),
        available_seats=available,
        total_seats=screen_row.get("total_seats"),
        ticket_prices=TicketPrices(
            normal=raw.get("ticket_price_normal") or raw.get("base_price"),
            student=raw.get("ticket_price_student"),
            member=raw.get("ticket_price_member"),
        ),
        total_time_commitment_minutes=ttc,
        risk_adjusted_quality_score=raqs,
    )


@router.get("/{showtime_id}/seats", response_model=SeatMapResponse)
async def get_showtime_seats(showtime_id: int):
    """Get seat map with availability.  Statuses: available | held | booked | disabled."""
    showtime = await crud_showtime.get_by_id(showtime_id)
    if not showtime:
        raise NotFoundException("Showtime", str(showtime_id))

    screen_id = showtime.get("screen_id")
    if not screen_id:
        raise NotFoundException("Screen for showtime", str(showtime_id))

    raw_seats = await crud_showtime.get_seat_map(screen_id)

    seats: list[SeatInMap] = []
    rows_seen: set[str] = set()
    max_seat_num = 0

    for s in raw_seats:
        spec_status = _STATUS_MAP.get(s.get("status", "available"), "available")
        rows_seen.add(s["row_label"])
        max_seat_num = max(max_seat_num, s.get("seat_number", 0))
        seats.append(SeatInMap(
            seat_id=s["id"],
            row_label=s["row_label"],
            seat_number=s["seat_number"],
            seat_type=s.get("seat_type") or "standard",
            status=spec_status,
        ))

    return SeatMapResponse(
        showtime_id=showtime_id,
        theatre_id=screen_id,
        layout=SeatLayout(rows=sorted(rows_seen), seats_per_row=max_seat_num),
        seats=seats,
    )


# ── Admin endpoints ───────────────────────────────────────────────────────────

@router.post("", response_model=Showtime, status_code=201)
async def create_showtime(showtime: ShowtimeCreate, _: object = Depends(get_admin_user)):
    """Create a new showtime — admin only."""
    return await crud_showtime.create(showtime)


@router.patch("/{showtime_id}", response_model=Showtime)
async def update_showtime(
    showtime_id: int,
    showtime: ShowtimeUpdate,
    _: object = Depends(get_admin_user),
):
    """Update showtime fields — admin only."""
    updated = await crud_showtime.update(showtime_id, showtime)
    if not updated:
        raise NotFoundException("Showtime", str(showtime_id))
    return updated


@router.delete("/{showtime_id}")
async def delete_showtime(showtime_id: int, _: object = Depends(get_admin_user)):
    """Cancel/remove a showtime — admin only."""
    success = await crud_showtime.delete(showtime_id)
    if not success:
        raise NotFoundException("Showtime", str(showtime_id))
    return {"message": "Showtime cancelled"}


@router.get("/movie/{movie_id}", response_model=List[Showtime])
async def get_showtimes_by_movie(movie_id: int):
    """Flat list of showtimes for a movie (prefer GET /movies/:id/showtimes for grouped + RAQS)."""
    showtimes = await crud_showtime.get_by_movie(movie_id)
    if not showtimes:
        raise NotFoundException("Showtimes for movie", str(movie_id))
    return showtimes
