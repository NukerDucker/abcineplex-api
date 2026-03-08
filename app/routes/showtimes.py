from fastapi import APIRouter, Depends, Query, HTTPException, status
from typing import List, Optional
from datetime import datetime, date, timedelta, timezone
from uuid import UUID
import asyncio
import logging

from app.crud.showtime import CRUDShowtime
from app.crud.booking import CRUDBooking
from app.schemas.showtime import (
    Showtime, ShowtimeCreate, ShowtimeUpdate,
    ShowtimeDetail, MovieRef, TheatreRef, TicketPrices,
    SeatMapResponse, SeatLayout, SeatInMap,
    TimeCommitmentResponse, TTCComponents,
)
from app.schemas.seat import (
    HoldRequest, HoldResponse, ReleaseHoldRequest, HoldStatusResponse,
    MAX_SEATS_PER_HOLD,
)
from app.schemas.booking import ReserveSeatRequest
from app.core.supabase import supabase_admin
from app.core.exceptions import NotFoundException, AppException
from app.core.security import get_current_user, get_admin_user, CurrentUser
from app.core.calculations import calc_raqs, calc_ttc, calc_demand_badge

logger = logging.getLogger(__name__)

_UTC_SUFFIX = "+00:00"

router = APIRouter(prefix="/api/v1/showtimes", tags=["showtimes"])
crud_showtime = CRUDShowtime(supabase_admin)
crud_booking = CRUDBooking(supabase_admin)


# ── Private helpers ───────────────────────────────────────────────────────────

def _parse_start_time(raw: Optional[str | datetime]) -> Optional[datetime]:
    if not raw:
        return None
    if isinstance(raw, str):
        return datetime.fromisoformat(raw.replace("Z", _UTC_SUFFIX))
    return raw


def _derive_times(
    start_dt: Optional[datetime], runtime: int, credits_min: int
) -> tuple[Optional[datetime], Optional[datetime]]:
    if not start_dt:
        return None, None
    end_dt = start_dt + timedelta(minutes=runtime)
    return end_dt, end_dt + timedelta(minutes=credits_min)


def _movie_raqs_ttc(movie_row: dict) -> tuple[float, int]:
    rating = float(movie_row.get("imdb_score") or 0)
    votes = int(movie_row.get("rating_count") or 0)
    rel_raw = movie_row.get("release_date")
    rel_date = date.fromisoformat(rel_raw) if isinstance(rel_raw, str) else rel_raw
    runtime = int(movie_row.get("duration_minutes") or 0)
    credits_min = int(movie_row.get("credits_duration_minutes") or 5)
    return calc_raqs(rating, votes, rel_date), calc_ttc(runtime, credits_min)


# ── Public: showtime detail & seat map ───────────────────────────────────────

@router.get("/{showtime_id}", response_model=ShowtimeDetail)
async def get_showtime(showtime_id: int):
    """Get full showtime detail including TTC and RAQS."""
    raw = await crud_showtime.get_detail(showtime_id)
    if not raw:
        raise NotFoundException("Showtime", str(showtime_id))

    movie_row = raw.get("movies") or {}
    runtime = int(movie_row.get("duration_minutes") or 0)
    credits_min = int(movie_row.get("credits_duration_minutes") or 5)

    start_dt = _parse_start_time(raw.get("start_time"))
    end_dt, end_credits_dt = _derive_times(start_dt, runtime, credits_min)
    raqs, ttc = _movie_raqs_ttc(movie_row)

    theatre_row = raw.get("theatres") or {}
    total_seats = theatre_row.get("total_seats") if isinstance(theatre_row, dict) else None
    available = await crud_showtime.get_showtime_availability(showtime_id)

    badge_data = calc_demand_badge(available, total_seats or 0)

    normal_price = float(raw.get("base_price") or 0.0)
    student_discount = raw.get("student_discount_baht")
    student_price = round(normal_price - float(student_discount or 0), 2) if student_discount is not None else None

    theatre_name = theatre_row.get("name") if isinstance(theatre_row, dict) else None
    if not theatre_name and theatre_id:
        theatre_name = f"Theatre {theatre_id}"

    return ShowtimeDetail(
        id=raw["id"],
        movie=MovieRef(id=movie_row.get("id", 0), title=movie_row.get("title", ""), runtime_minutes=runtime) if movie_row else None,
        theatre=TheatreRef(id=theatre_id, name=theatre_name) if theatre_id else None,
        start_time=start_dt,
        end_time=end_dt,
        estimated_end_with_credits=end_credits_dt,
        language=raw.get("language"),
        available_seats=available,
        total_seats=total_seats,
        base_price=normal_price,
        student_discount_baht=student_discount,
        member_discount_baht=raw.get("member_discount_baht"),
        ticket_prices=TicketPrices(normal=normal_price, student=student_price),
        total_time_commitment_minutes=ttc,
        risk_adjusted_quality_score=raqs,
        **badge_data,
    )


@router.get("/{showtime_id}/seats", response_model=SeatMapResponse)
async def get_showtime_seats(showtime_id: int):
    """Get seat map with availability.  Statuses: available | held | booked | disabled."""
    # Cancel any expired holds in the DB before computing availability
    await crud_booking.release_expired_reservations()

    showtime = await crud_showtime.get_by_id(showtime_id)
    if not showtime:
        raise NotFoundException("Showtime", str(showtime_id))

    theatre_id = showtime.get("theatre_id")
    if not theatre_id:
        raise NotFoundException("Screen for showtime", str(showtime_id))

    raw_seats = await crud_showtime.get_seat_map(theatre_id, showtime_id)
    seats: list[SeatInMap] = []
    rows_seen: set[str] = set()
    max_seat_num = 0

    for s in raw_seats:
        rows_seen.add(s["row_label"])
        max_seat_num = max(max_seat_num, s.get("seat_number", 0))
        seats.append(SeatInMap(
            seat_id=s["id"],
            row_label=s["row_label"],
            seat_number=s["seat_number"],
            status=s.get("status", "available"),
        ))

    return SeatMapResponse(
        showtime_id=showtime_id,
        theatre_id=theatre_id,
        layout=SeatLayout(rows=sorted(rows_seen), seats_per_row=max_seat_num),
        seats=seats,
    )


# ── Seat hold endpoints (5.5) ─────────────────────────────────────────────────

@router.post("/{showtime_id}/seats/hold", response_model=HoldResponse)
async def hold_seats(
    showtime_id: int,
    body: HoldRequest,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Place a 5-minute hold on selected seats.

    Implementation: DB-backed via reserve_seats RPC (payment_deadline = now+5min).
    hold_id is the resulting booking/reservation ID.
    """
    if len(body.seat_ids) > MAX_SEATS_PER_HOLD:
        raise AppException(
            f"Cannot hold more than {MAX_SEATS_PER_HOLD} seats per transaction", 400
        )

    # Release any stale holds before checking availability
    await crud_booking.release_expired_reservations()

    showtime = await crud_showtime.get_by_id(showtime_id)
    if not showtime:
        raise NotFoundException("Showtime", str(showtime_id))

    base_price = float(showtime.get("base_price") or 0)

    # Fetch movie discount flags
    movie_id = showtime.get("movie_id")
    movie: dict = {}
    if movie_id:
        movie_res = await asyncio.to_thread(
            lambda: supabase_admin.table("movies")
                .select("allow_student_discount, allow_member_discount")
                .eq("id", movie_id)
                .maybe_single()
                .execute()
        )
        movie = movie_res.data or {}

    # Fetch calling user's eligibility fields from DB (never trust client-supplied values)
    user_res = await asyncio.to_thread(
        lambda: supabase_admin.table("users")
            .select("is_student, student_id_verified, membership_tier")
            .eq("id", current_user.user_id)
            .maybe_single()
            .execute()
    )
    user = user_res.data or {}

    # Compute price per spec: student > member > normal
    if body.ticket_type == 'student':
        is_eligible_student = bool(user.get("is_student")) and bool(user.get("student_id_verified"))
        movie_allows_discount = bool(movie.get("allow_student_discount"))
        if not is_eligible_student or not movie_allows_discount:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not eligible for student discount on this movie",
            )
        price = base_price - float(showtime.get("student_discount_baht") or 0)
    elif (user.get("membership_tier") or "free") != "free" and movie.get("allow_member_discount"):
        # Member discount applied automatically for eligible members buying normal tickets
        price = base_price - float(showtime.get("member_discount_baht") or 0)
    else:
        price = base_price

    req = ReserveSeatRequest(
        showtime_id=showtime_id,
        seat_ids=body.seat_ids,
        price_per_seat=price,
        ticket_type=body.ticket_type,
    )
    result = await crud_booking.reserve_seats(req, user_id=current_user.user_id)

    if not result.get("success"):
        error = result.get("error", "Seats unavailable")
        unavailable = result.get("unavailable_seats", [])
        if unavailable:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"message": error, "unavailable_seats": unavailable},
            )
        raise AppException(error, 400)

    hold_id = str(result["booking_id"])
    expires_at_raw = result.get("payment_deadline")
    if isinstance(expires_at_raw, str):
        expires_at = datetime.fromisoformat(expires_at_raw.replace("Z", _UTC_SUFFIX))
    else:
        expires_at = expires_at_raw or datetime.now(timezone.utc) + timedelta(seconds=300)

    now = datetime.now(timezone.utc)
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    expires_in = max(0, int((expires_at - now).total_seconds()))

    return HoldResponse(
        hold_id=hold_id,
        seat_ids=body.seat_ids,
        expires_at=expires_at,
        expires_in_seconds=expires_in,
    )


@router.delete("/{showtime_id}/seats/hold")
async def release_hold(
    showtime_id: int,  # kept for URL symmetry; hold_id is the real identifier
    body: ReleaseHoldRequest,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Release a seat hold manually (e.g., user navigates back)."""
    hold_id = body.hold_id  # UUID string

    # Verify ownership before releasing
    booking = await crud_booking.get_booking_by_id(hold_id)
    if not booking:
        raise NotFoundException("Hold", hold_id)
    if str(booking.get("user_id")) != current_user.user_id and not current_user.is_admin:
        raise AppException("Not authorised to release this hold", 403)

    result = await crud_booking.cancel_booking(hold_id)
    if not result.get("success"):
        raise AppException(result.get("error", "Failed to release hold"), 400)

    return {"message": "Hold released"}


@router.get("/{showtime_id}/seats/hold/status", response_model=HoldStatusResponse)
async def get_hold_status(
    showtime_id: int,
    hold_id: str = Query(..., description="Hold ID returned by POST /seats/hold"),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Check hold expiry status (for countdown timer on frontend)."""
    booking = await crud_booking.get_booking_by_id(hold_id)
    if not booking:
        return HoldStatusResponse(hold_id=hold_id, is_active=False, expires_in_seconds=0)

    if booking.get("booking_status") != "pending":
        return HoldStatusResponse(hold_id=hold_id, is_active=False, expires_in_seconds=0)

    deadline_raw = booking.get("payment_deadline")
    if not deadline_raw:
        return HoldStatusResponse(hold_id=hold_id, is_active=False, expires_in_seconds=0)

    if isinstance(deadline_raw, str):
        deadline = datetime.fromisoformat(deadline_raw.replace("Z", _UTC_SUFFIX))
    else:
        deadline = deadline_raw

    now = datetime.now(timezone.utc)
    if deadline.tzinfo is None:
        deadline = deadline.replace(tzinfo=timezone.utc)

    remaining = int((deadline - now).total_seconds())
    is_active = remaining > 0

    return HoldStatusResponse(
        hold_id=hold_id,
        is_active=is_active,
        expires_in_seconds=max(0, remaining),
    )


@router.get("/{showtime_id}/demand")
async def get_showtime_demand(showtime_id: int):
    """Convenience endpoint — demand badge for a showtime."""
    raw = await crud_showtime.get_detail(showtime_id)
    if not raw:
        raise NotFoundException("Showtime", str(showtime_id))

    theatre_row = raw.get("theatres") or {}
    total = theatre_row.get("total_seats") if isinstance(theatre_row, dict) else None
    available = await crud_showtime.get_showtime_availability(showtime_id)

    return {"showtime_id": showtime_id, **calc_demand_badge(available, total or 0)}


@router.get("/{showtime_id}/time-commitment", response_model=TimeCommitmentResponse)
async def get_showtime_time_commitment(
    showtime_id: int,
    travel_minutes: int = Query(30, ge=0, le=120, description="One-way travel time in minutes (default: 30)"),
):
    """Get Total Time Commitment calculation for a showtime with detailed breakdown."""
    showtime = await crud_showtime.get_by_id(showtime_id)
    if not showtime:
        raise NotFoundException("Showtime", str(showtime_id))

    # Get movie details for runtime and credits
    movie_id = showtime.get("movie_id")
    if not movie_id:
        raise NotFoundException("Movie for showtime", str(showtime_id))

    # Import here to avoid circular imports
    from app.crud.movie import CRUDMovie
    crud_movie = CRUDMovie(supabase_admin)
    movie = await crud_movie.get_by_id(movie_id)
    if not movie:
        raise NotFoundException("Movie", str(movie_id))

    # Extract movie details
    runtime = int(movie.get("duration_minutes") or 0)
    credits_min = int(movie.get("credits_duration_minutes") or 5)
    movie_title = movie.get("title", "")

    # Calculate TTC
    ttc = calc_ttc(runtime, credits_min, travel_minutes)
    pre_show_ads = 15  # Fixed constant

    # Parse showtime start
    start_raw = showtime.get("start_time", "")
    if isinstance(start_raw, str):
        try:
            show_start = datetime.fromisoformat(start_raw.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            show_start = datetime.now(timezone.utc)
    else:
        show_start = start_raw if isinstance(start_raw, datetime) else datetime.now(timezone.utc)

    # Calculate end times
    movie_end_time = show_start + timedelta(minutes=runtime)
    credits_end_time = show_start + timedelta(minutes=runtime + credits_min)
    home_arrival = show_start + timedelta(minutes=ttc)

    return TimeCommitmentResponse(
        showtime_id=showtime_id,
        movie_title=movie_title,
        components=TTCComponents(
            travel_to_theatre_minutes=travel_minutes,
            pre_show_ads_minutes=pre_show_ads,
            runtime_minutes=runtime,
            credits_minutes=credits_min,
            travel_from_theatre_minutes=travel_minutes,
        ),
        total_time_commitment_minutes=ttc,
        show_start=show_start,
        movie_end_time=movie_end_time,
        credits_end_time=credits_end_time,
        estimated_home_arrival=home_arrival,
    )


# ── Admin endpoints ───────────────────────────────────────────────────────────
# Moved to /api/v1/admin/showtimes in app/routes/admin.py

@router.get("/movie/{movie_id}", response_model=List[Showtime])
async def get_showtimes_by_movie(movie_id: int):
    """Flat list of showtimes for a movie (prefer GET /movies/:id/showtimes for grouped + RAQS)."""
    showtimes = await crud_showtime.get_by_movie(movie_id)
    if not showtimes:
        raise NotFoundException("Showtimes for movie", str(movie_id))
    return showtimes
