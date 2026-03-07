"""
Admin Portal API Routes — Consolidated under /api/v1/admin/
All endpoints require admin privileges.
"""
from fastapi import APIRouter, Query, Depends, HTTPException, status, Body
from typing import Optional, List
from uuid import UUID
from pydantic import BaseModel
import asyncio
import secrets as _secrets

from app.crud.movie import CRUDMovie
from app.crud.showtime import CRUDShowtime
from app.crud.booking import CRUDBooking
from app.crud.user import CRUDUser
from app.crud.public import CRUDPublic
from app.crud.theatre import CRUDTheatre, CRUDSeat
from app.crud.showtime_seat import CRUDShowtimeSeat
from app.schemas.movie import Movie, MovieCreate, MovieUpdate
from app.schemas.showtime import Showtime, ShowtimeCreate, ShowtimeUpdate
from app.schemas.showtime_seat import ShowtimeSeat, ShowtimeSeatCreate, ShowtimeSeatUpdate
from app.schemas.user import AdminUserResponse, AdminUserUpdate, AdminPointTransaction, AdminPointTransactionsResponse
from app.schemas.public import HeroSlide, HeroSlideCreate, HeroSlideUpdate, Promotion, PromotionCreate, PromotionUpdate
from app.schemas.theatre import Theatre, TheatreCreate, TheatreUpdate, Seat, SeatCreate, SeatUpdate
from app.core.supabase import supabase_admin
from app.core.security import get_admin_user, CurrentUser
from app.core.exceptions import NotFoundException

import logging

logger = logging.getLogger(__name__)

# All admin routes require admin auth at router level
router = APIRouter(
    prefix="/api/v1/admin",
    tags=["admin"],
    dependencies=[Depends(get_admin_user)]
)

crud_movie = CRUDMovie(supabase_admin)
crud_showtime = CRUDShowtime(supabase_admin)
crud_booking = CRUDBooking(supabase_admin)
crud_user = CRUDUser(supabase_admin)
crud_public = CRUDPublic(supabase_admin)
crud_theatre = CRUDTheatre(supabase_admin)
crud_seat = CRUDSeat(supabase_admin)
crud_showtime_seat = CRUDShowtimeSeat(supabase_admin)


# ========== Dashboard ==========

@router.get("/dashboard")
async def get_admin_dashboard():
    """Get admin dashboard statistics"""
    from datetime import date, datetime, timezone
    today_str = date.today().isoformat()
    today_start = f"{today_str}T00:00:00+07:00"
    today_end = f"{today_str}T23:59:59+07:00"

    try:
        # Bookings confirmed today (use created_at — updated_at may not be set by RPC)
        bk_res = await asyncio.to_thread(
            lambda: supabase_admin.table("bookings")
                .select("total_amount, final_amount_paid", count="exact")
                .eq("booking_status", "confirmed")
                .gte("created_at", today_start)
                .lte("created_at", today_end)
                .execute()
        )
        total_bookings_today = bk_res.count or 0
        revenue_today = sum(
            float(r.get("final_amount_paid") or r.get("total_amount") or 0)
            for r in (bk_res.data or [])
        )

        # Movies now showing
        now_res = await asyncio.to_thread(
            lambda: supabase_admin.table("movies")
                .select("id", count="exact")
                .eq("release_status", "now_showing")
                .execute()
        )
        movies_now_showing = now_res.count or 0

        # Upcoming movies
        up_res = await asyncio.to_thread(
            lambda: supabase_admin.table("movies")
                .select("id", count="exact")
                .eq("release_status", "upcoming")
                .execute()
        )
        upcoming_movies = up_res.count or 0

        # Total users
        users_res = await asyncio.to_thread(
            lambda: supabase_admin.table("users")
                .select("id", count="exact")
                .execute()
        )
        total_users = users_res.count or 0

        # Seat fill: count showtime_seats for today's showtimes via theatres.total_seats
        seats_filled_percent = 0.0
        st_res = await asyncio.to_thread(
            lambda: supabase_admin.table("showtimes")
                .select("id, theatres(total_seats)")
                .gte("start_time", today_start)
                .lte("start_time", today_end)
                .execute()
        )
        if st_res.data:
            showtime_ids = [s["id"] for s in st_res.data]
            total_seats = sum(
                int((s.get("theatres") or {}).get("total_seats") or 0)
                for s in st_res.data
            )
            if total_seats > 0 and showtime_ids:
                # Count booked seats (is_available=false) across these showtimes
                booked_res = await asyncio.to_thread(
                    lambda: supabase_admin.table("showtime_seats")
                        .select("seat_id", count="exact")
                        .in_("showtime_id", showtime_ids)
                        .eq("is_available", False)
                        .execute()
                )
                booked = booked_res.count or 0
                seats_filled_percent = round((booked / total_seats) * 100, 1)

        # All-time confirmed bookings + revenue
        all_bk_res = await asyncio.to_thread(
            lambda: supabase_admin.table("bookings")
                .select("final_amount_paid", count="exact")
                .eq("booking_status", "confirmed")
                .execute()
        )
        total_confirmed_bookings = all_bk_res.count or 0
        total_revenue_alltime = sum(
            float(r.get("final_amount_paid") or 0) for r in (all_bk_res.data or [])
        )

        # Pending bookings count
        pending_res = await asyncio.to_thread(
            lambda: supabase_admin.table("bookings")
                .select("id", count="exact")
                .eq("booking_status", "pending")
                .execute()
        )
        pending_bookings = pending_res.count or 0

        # Snack orders confirmed today
        snack_res = await asyncio.to_thread(
            lambda: supabase_admin.table("orders")
                .select("total_amount", count="exact")
                .eq("order_status", "confirmed")
                .gte("created_at", today_start)
                .lte("created_at", today_end)
                .execute()
        )
        snack_orders_today = snack_res.count or 0
        snack_revenue_today = sum(
            float(r.get("total_amount") or 0) for r in (snack_res.data or [])
        )

        # Recent 5 confirmed bookings
        recent_res = await asyncio.to_thread(
            lambda: supabase_admin.table("bookings")
                .select(
                    "id, total_amount, created_at, "
                    "showtimes!bookings_showtime_id_fkey(movies(title))"
                )
                .eq("booking_status", "confirmed")
                .order("created_at", desc=True)
                .limit(5)
                .execute()
        )
        recent_bookings = [
            {
                "id": r["id"],
                "movie_title": ((r.get("showtimes") or {}).get("movies") or {}).get("title"),
                "total_amount": float(r.get("total_amount") or 0),
                "created_at": r.get("created_at"),
            }
            for r in (recent_res.data or [])
        ]

        return {
            "total_bookings_today": total_bookings_today,
            "revenue_today": round(revenue_today, 2),
            "movies_now_showing": movies_now_showing,
            "upcoming_movies": upcoming_movies,
            "total_users": total_users,
            "seats_filled_percent": seats_filled_percent,
            "total_confirmed_bookings": total_confirmed_bookings,
            "total_revenue_alltime": round(total_revenue_alltime, 2),
            "pending_bookings": pending_bookings,
            "snack_orders_today": snack_orders_today,
            "snack_revenue_today": round(snack_revenue_today, 2),
            "recent_bookings": recent_bookings,
        }
    except Exception as e:
        logger.error(f"Error fetching dashboard stats: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch dashboard statistics"
        )


# ========== Movie Management ==========

@router.get("/movies", response_model=List[Movie])
async def list_admin_movies():
    """List all movies (all statuses, including hidden)"""
    try:
        rows, _ = await crud_movie.get_multi(page=1, limit=500, active_only=False)
        return rows
    except Exception as e:
        logger.error(f"Error fetching admin movie list: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch movies"
        )


@router.get("/movies/tmdb/{tmdb_id}")
async def fetch_tmdb_movie(tmdb_id: int):
    """Fetch movie data from TMDB API with Thai release date."""
    from app.core.config import settings
    import httpx
    from datetime import date as date_type

    if not settings.tmdb_api_key:
        raise HTTPException(status_code=503, detail="TMDB API key not configured")

    url = f"{settings.tmdb_base_url}/movie/{tmdb_id}"
    params = {
        "api_key": settings.tmdb_api_key,
        "append_to_response": "credits,videos,release_dates",  # ← Add release_dates
        "language": "en-US",
    }

    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(url, params=params)
        if resp.status_code == 404:
            raise HTTPException(status_code=404, detail=f"TMDB movie {tmdb_id} not found")
        if resp.status_code != 200:
            raise HTTPException(status_code=502, detail="TMDB API error")
        data = resp.json()

    # ── Thai release date from release_dates ──────────────────────────────
    thai_release_date_str = None
    thai_certification = ""  # content rating e.g. "G", "13+", "18+"

    if release_dates := data.get("release_dates"):
        for entry in release_dates.get("results") or []:
            if entry.get("iso_3166_1") == "TH":          # ← Thailand region
                releases = entry.get("release_dates") or []
                if releases:
                    # Prefer type 3 (Theatrical) > type 4 (Digital) > first available
                    # TMDB release types: 1=Premiere,2=Limited,3=Theatrical,4=Digital,5=Physical,6=TV
                    theatrical = next((r for r in releases if r.get("type") == 3), None)
                    chosen = theatrical or releases[0]
                    raw = chosen.get("release_date") or ""
                    thai_release_date_str = raw[:10] if raw else None  # trim to YYYY-MM-DD
                    thai_certification = chosen.get("certification") or ""
                break

    # Fall back to global release_date if Thailand has no entry
    release_date_str = thai_release_date_str or data.get("release_date") or ""

    # ── Release status based on Thai date ────────────────────────────────
    release_status = "upcoming"
    if release_date_str:
        try:
            rd = date_type.fromisoformat(release_date_str)
            release_status = "now_showing" if rd <= date_type.today() else "upcoming"
        except ValueError:
            pass

    # ── Director and starring from credits ───────────────────────────────
    director = None
    starring: list[str] = []
    if credits := data.get("credits"):
        crew = credits.get("crew") or []
        cast = credits.get("cast") or []
        directors = [c["name"] for c in crew if c.get("job") == "Director"]
        director = directors[0] if directors else None
        starring = [c["name"] for c in cast[:8]]

    # ── Trailer from videos ──────────────────────────────────────────────
    trailer_url = None
    if videos := data.get("videos"):
        for v in (videos.get("results") or []):
            if v.get("site") == "YouTube" and v.get("type") == "Trailer":
                trailer_url = f"https://www.youtube.com/watch?v={v['key']}"
                break

    # ── Genre ────────────────────────────────────────────────────────────
    genres = data.get("genres") or []
    genre_list = [g["name"] for g in genres]

    poster_path = data.get("poster_path")
    backdrop_path = data.get("backdrop_path")
    poster_url = f"{settings.tmdb_image_base_url}w500{poster_path}" if poster_path else None
    banner_url = f"{settings.tmdb_image_base_url}w500{backdrop_path}" if backdrop_path else None
    runtime = data.get("runtime") or 0

    print()
    return {
        "title": data.get("title", ""),
        "synopsis": data.get("overview"),
        "release_date": release_date_str,         # ← Thai date (fallback: global)
        "runtime_minutes": runtime,
        "duration_minutes": runtime + 15,
        "credits_duration_minutes": 5,
        "imdb_score": data.get("vote_average"),
        "rating_count": data.get("vote_count"),
        "genre": genre_list,
        "director": director,
        "starring": starring,
        "poster_url": poster_url,
        "banner_url": banner_url,
        "trailer_url": trailer_url,
        "release_status": release_status,
        "content_rating": thai_certification,     # ← Thai rating (e.g. "13+")
        "is_active": True,
    }

@router.post("/movies", response_model=Movie, status_code=201)
async def create_admin_movie(movie: MovieCreate):
    """Add a new movie"""
    return await crud_movie.create(movie)


@router.patch("/movies/{movie_id}", response_model=Movie)
async def update_admin_movie(movie_id: int, movie: MovieUpdate):
    """Update movie info"""
    updated = await crud_movie.update(movie_id, movie)
    if not updated:
        raise NotFoundException("Movie", str(movie_id))
    return updated


@router.delete("/movies/{movie_id}")
async def delete_admin_movie(movie_id: int):
    """Remove a movie listing (soft delete: set release_status to 'ended')"""
    res = await asyncio.to_thread(
        lambda: supabase_admin.table("movies")
            .update({"release_status": "ended", "is_active": False})
            .eq("id", movie_id)
            .execute()
    )
    if not res.data:
        raise NotFoundException("Movie", str(movie_id))
    return {"message": "Movie removed"}


@router.post("/movies/recalculate-consensus")
async def recalculate_consensus_scores():
    """Recalculate Consensus AI scores for all active movies."""
    count = await crud_movie.recalculate_all_consensus_scores()
    return {"message": f"Recalculated consensus scores for {count} movies", "count": count}


# ========== Showtime Management ==========

@router.post("/showtimes", response_model=Showtime, status_code=201)
async def create_admin_showtime(showtime: ShowtimeCreate):
    """Create a new showtime for a movie"""
    try:
        # Validate required fields
        if not showtime.movie_id or showtime.movie_id == 0:
            raise ValueError("movie_id is required and must be greater than 0")
        if not showtime.theatre_id or showtime.theatre_id == 0:
            raise ValueError("theatre_id is required and must be greater than 0")
        if not showtime.start_time:
            raise ValueError("start_time is required")
        if showtime.base_price <= 0:
            raise ValueError("base_price must be greater than 0")

        return await crud_showtime.create(showtime)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e)
        )


@router.patch("/showtimes/{showtime_id}", response_model=Showtime)
async def update_admin_showtime(showtime_id: int, showtime: ShowtimeUpdate):
    """Update showtime details"""
    updated = await crud_showtime.update(showtime_id, showtime)
    if not updated:
        raise NotFoundException("Showtime", str(showtime_id))
    return updated


@router.delete("/showtimes/{showtime_id}")
async def delete_admin_showtime(showtime_id: int):
    """Cancel/remove a showtime (soft delete: set is_active = false)"""
    res = await asyncio.to_thread(
        lambda: supabase_admin.table("showtimes")
            .update({"is_active": False})
            .eq("id", showtime_id)
            .execute()
    )
    if not res.data:
        raise NotFoundException("Showtime", str(showtime_id))
    return {"message": "Showtime cancelled"}


# ========== Booking Management ==========

@router.get("/bookings")
async def list_admin_bookings(
    user_id: Optional[UUID] = Query(None),
    showtime_id: Optional[int] = Query(None),
    booking_status: Optional[str] = Query(None),
    date: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0)
):
    """List all bookings with user name/email."""
    try:
        def _fetch():
            q = supabase_admin.table("bookings").select(
                "id, user_id, booking_status, num_tickets, total_amount, final_amount_paid, "
                "points_redeemed, created_at, updated_at, change_count, "
                "users!inner(full_name, email, phone), "
                "showtimes!bookings_showtime_id_fkey(id, start_time, end_time, "
                "movies(id, title), theatres(name)), "
                "booking_seats(seat_id, seats(row_label, seat_number)), "
                "payments(payment_method, status, created_at)"
            ).order("created_at", desc=True).limit(limit).offset(offset)
            if booking_status:
                q = q.eq("booking_status", booking_status)
            return q.execute()

        res = await asyncio.to_thread(_fetch)

        bookings = []
        for row in (res.data or []):
            user     = row.get("users") or {}
            showtime = row.get("showtimes") or {}
            movie    = showtime.get("movies") or {}
            theatre  = showtime.get("theatres") or {}
            seats = [
                f"{(bs.get('seats') or {}).get('row_label', '')}{(bs.get('seats') or {}).get('seat_number', '')}"
                for bs in (row.get("booking_seats") or [])
            ]
            # payments is a list; find the confirmed/succeeded one
            payments = row.get("payments") or []
            paid_payment = next(
                (p for p in payments if p.get("status") in ("succeeded", "completed")),
                payments[0] if payments else {}
            )
            bookings.append({
                "booking_id":       row["id"],
                "id":               row["id"],
                "user_id":          row["user_id"],
                "full_name":        user.get("full_name"),
                "email":            user.get("email"),
                "phone":            user.get("phone"),
                "booking_status":   row["booking_status"],
                "num_tickets":      row.get("num_tickets"),
                "total_amount":     row.get("total_amount"),
                "final_amount_paid":row.get("final_amount_paid"),
                "points_redeemed":  row.get("points_redeemed"),
                "showtime_id":      showtime.get("id"),
                "showtime_start":   showtime.get("start_time"),
                "showtime_end":     showtime.get("end_time"),
                "movie_title":      movie.get("title"),
                "movie_id":         movie.get("id"),
                "screen_name":      theatre.get("name"),
                "seats":            seats,
                "created_at":       row.get("created_at"),
                "change_count":     row.get("change_count"),
                "payment_method":   paid_payment.get("payment_method"),
                "payment_status":   paid_payment.get("status"),
                "paid_at":          paid_payment.get("created_at"),
            })
        return {"bookings": bookings, "count": len(bookings)}
    except Exception as e:
        logger.error(f"Error fetching bookings: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch bookings"
        )


# ========== Snack Order Management ==========

@router.get("/orders")
async def list_admin_orders(
    order_status: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
):
    """List all snack orders with user name/email."""
    try:
        def _fetch():
            q = supabase_admin.table("orders").select(
                "id, user_id, order_status, total_amount, created_at, "
                "users!fk_orders_user_id_users_id(email, full_name), "
                "order_items(product_id, quantity, unit_price)"
            ).order("created_at", desc=True).limit(limit).offset(offset)
            if order_status:
                q = q.eq("order_status", order_status)
            return q.execute()

        res = await asyncio.to_thread(_fetch)

        orders = []
        for row in (res.data or []):
            user = row.get("users") or {}
            items = [
                {
                    "product_id": item["product_id"],
                    "quantity":   item["quantity"],
                    "unit_price": float(item.get("unit_price") or 0),
                    "subtotal":   item["quantity"] * float(item.get("unit_price") or 0),
                }
                for item in (row.get("order_items") or [])
            ]
            orders.append({
                "id":             row["id"],
                "user_id":        row["user_id"],
                "user_email":     user.get("email"),
                "user_full_name": user.get("full_name"),
                "status":         row["order_status"],
                "total_amount":   row["total_amount"],
                "items":          items,
                "created_at":     row["created_at"],
            })
        return {"orders": orders, "count": len(orders)}
    except Exception as e:
        logger.error(f"list_admin_orders error: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch orders")


class AdminBookingUpdate(BaseModel):
    new_showtime_id: Optional[int] = None
    new_seat_ids: Optional[List[int]] = None
    admin_note: Optional[str] = None


@router.patch("/bookings/{booking_id}")
async def update_admin_booking(
    booking_id: str,
    body: AdminBookingUpdate,
):
    """Admin changes seat or showtime for a customer booking (no time restrictions)."""
    booking_res = await asyncio.to_thread(
        lambda: supabase_admin.table("bookings")
            .select("*")
            .eq("id", booking_id)
            .maybe_single()
            .execute()
    )
    if not booking_res.data:
        raise HTTPException(status_code=404, detail="Booking not found")
    b = booking_res.data

    if not body.new_showtime_id and not body.new_seat_ids:
        raise HTTPException(status_code=400, detail="Provide new_showtime_id and/or new_seat_ids")

    target_showtime_id = body.new_showtime_id or b["showtime_id"]

    # Validate new showtime if provided
    if body.new_showtime_id:
        st_res = await asyncio.to_thread(
            lambda: supabase_admin.table("showtimes")
                .select("id")
                .eq("id", body.new_showtime_id)
                .maybe_single()
                .execute()
        )
        if not st_res.data:
            raise HTTPException(status_code=404, detail="New showtime not found")

    # Check seat conflicts if new seats provided
    if body.new_seat_ids:
        other_bookings_res = await asyncio.to_thread(
            lambda: supabase_admin.table("bookings")
                .select("id")
                .eq("showtime_id", target_showtime_id)
                .neq("id", booking_id)
                .in_("booking_status", ["confirmed", "changed", "pending"])
                .execute()
        )
        other_ids = [row["id"] for row in (other_bookings_res.data or [])]
        if other_ids:
            taken_res = await asyncio.to_thread(
                lambda: supabase_admin.table("booking_seats")
                    .select("seat_id")
                    .in_("booking_id", other_ids)
                    .in_("seat_id", body.new_seat_ids)
                    .execute()
            )
            taken = {row["seat_id"] for row in (taken_res.data or [])}
            if taken:
                raise HTTPException(status_code=409, detail=f"Seats {sorted(taken)} are not available")

    # Apply showtime change
    update_data: dict = {}
    if body.new_showtime_id:
        update_data["showtime_id"] = body.new_showtime_id
        update_data["original_showtime_id"] = b["showtime_id"]
        # Only promote to 'changed' if already confirmed — pending stays pending
        if b.get("booking_status") == "confirmed":
            update_data["booking_status"] = "changed"

    if update_data:
        await asyncio.to_thread(
            lambda: supabase_admin.table("bookings")
                .update(update_data)
                .eq("id", booking_id)
                .execute()
        )

    # Apply seat change if requested
    if body.new_seat_ids:
        await asyncio.to_thread(
            lambda: supabase_admin.table("booking_seats")
                .delete()
                .eq("booking_id", booking_id)
                .execute()
        )
        new_booking_seats = [
            {"booking_id": booking_id, "seat_id": sid, "showtime_id": target_showtime_id}
            for sid in body.new_seat_ids
        ]
        await asyncio.to_thread(
            lambda: supabase_admin.table("booking_seats").insert(new_booking_seats).execute()
        )

        # Recreate tickets
        tickets_res = await asyncio.to_thread(
            lambda: supabase_admin.table("tickets")
                .select("ticket_type, price_paid")
                .eq("booking_id", booking_id)
                .execute()
        )
        existing = tickets_res.data or []
        if existing:
            await asyncio.to_thread(
                lambda: supabase_admin.table("tickets")
                    .delete()
                    .eq("booking_id", booking_id)
                    .execute()
            )
            new_tickets = []
            for i, sid in enumerate(body.new_seat_ids):
                old_t = existing[i] if i < len(existing) else existing[-1]
                new_tickets.append({
                    "booking_id": booking_id,
                    "seat_id": sid,
                    "ticket_type": old_t.get("ticket_type", "normal"),
                    "price_paid": old_t.get("price_paid", 0),
                    "qr_code_slug": _secrets.token_urlsafe(12),
                })
            await asyncio.to_thread(
                lambda: supabase_admin.table("tickets").insert(new_tickets).execute()
            )

    updated = await asyncio.to_thread(
        lambda: supabase_admin.table("bookings")
            .select("*")
            .eq("id", booking_id)
            .maybe_single()
            .execute()
    )
    return updated.data or {}


# ========== Review Moderation ==========

@router.get("/reviews")
async def list_admin_reviews(
    movie_id: Optional[int] = Query(None),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    """List all reviews for admin moderation, optionally filtered by movie."""
    try:
        query = supabase_admin.table("movie_reviews").select(
            "id, user_id, movie_id, rating, review_text, like_count, created_at, "
            "users!inner(user_name, email), movies!inner(title)",
            count="exact",
        )
        if movie_id:
            query = query.eq("movie_id", movie_id)
        res = await asyncio.to_thread(
            lambda: query.order("created_at", desc=True).range(offset, offset + limit - 1).execute()
        )
        return {"reviews": res.data or [], "total": res.count or 0}
    except Exception as e:
        logger.error(f"Error fetching reviews for admin: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to fetch reviews")


@router.delete("/reviews/{review_id}")
async def admin_delete_review(review_id: int):
    """Delete any review regardless of ownership (content moderation)."""
    res = await asyncio.to_thread(
        lambda: supabase_admin.table("movie_reviews").delete().eq("id", review_id).execute()
    )
    if not res.data:
        raise NotFoundException("Review", str(review_id))
    return {"status": "success", "message": "Review deleted"}


# ========== User Management ==========

@router.get("/users", response_model=List[AdminUserResponse])
async def list_admin_users(
    search: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000)
):
    """List all users with optional search"""
    try:
        # TODO: Add search parameter support to CRUD
        users = await crud_user.get_multi(skip, limit)
        return users
    except Exception as e:
        logger.error(f"Error fetching users: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch users"
        )


@router.patch("/users/{user_id}", response_model=AdminUserResponse)
async def update_admin_user(user_id: UUID, user_update: AdminUserUpdate):
    """Edit customer information including membership and student discount.
    When loyalty_points is changed, a membership_transactions row is inserted with the given reason.
    """
    user_uuid = str(user_id)
    data = user_update.model_dump(exclude_unset=True)
    reason = data.pop("points_adjustment_reason", None)

    # Snapshot current points before update so we can compute the delta
    points_delta: Optional[int] = None
    if "loyalty_points" in data:
        current_res = await asyncio.to_thread(
            lambda: supabase_admin.table("users")
                .select("loyalty_points")
                .eq("id", user_uuid)
                .maybe_single()
                .execute()
        )
        current_pts = (current_res.data or {}).get("loyalty_points") or 0
        points_delta = data["loyalty_points"] - current_pts

    updated = await crud_user.update(user_uuid, data)
    if not updated:
        raise NotFoundException("User", str(user_id))

    # Log the adjustment to membership_transactions
    if points_delta is not None:
        adj_reason = reason or "admin_adjustment"
        try:
            await asyncio.to_thread(
                lambda: supabase_admin.table("membership_transactions")
                    .insert({"user_id": user_uuid, "points_delta": points_delta, "reason": adj_reason, "reference_id": user_uuid})
                    .execute()
            )
        except Exception as e:
            logger.warning(f"Could not log admin points adjustment: {e}")

    return updated


@router.delete("/users/{user_id}")
async def delete_admin_user(user_id: UUID):
    """Deactivate a user"""
    user_uuid = str(user_id)
    success = await crud_user.deactivate(user_uuid)
    if not success:
        raise NotFoundException("User", str(user_id))
    return {"message": "User deactivated"}


# ========== Point Transactions ==========

@router.get("/point-transactions", response_model=AdminPointTransactionsResponse)
async def list_admin_point_transactions(
    user_id: Optional[str] = Query(None),
    reason: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    """Paginated list of all membership_transactions for admin audit."""
    try:
        def _fetch():
            q = supabase_admin.table("membership_transactions").select(
                "id, user_id, points_delta, reason, reference_id, created_at, "
                "users!fk_membership_transactions_user_id_users_id(email, full_name)",
                count="exact",
            )
            if user_id:
                q = q.eq("user_id", user_id)
            if reason:
                q = q.eq("reason", reason)
            return q.order("created_at", desc=True).range(offset, offset + limit - 1).execute()

        res = await asyncio.to_thread(_fetch)

        transactions = []
        for row in (res.data or []):
            user_info = row.get("users") or {}
            transactions.append(AdminPointTransaction(
                id            = row["id"],
                user_id       = row["user_id"],
                user_email    = user_info.get("email", ""),
                user_full_name= user_info.get("full_name"),
                points_delta  = row["points_delta"],
                reason        = row["reason"],
                reference_id  = row.get("reference_id"),
                created_at    = row.get("created_at"),
            ))
        return AdminPointTransactionsResponse(transactions=transactions, total=res.count or 0)
    except Exception as e:
        logger.error(f"list_admin_point_transactions error: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch point transactions")


# ========== Public Content Management (CMS) ==========

@router.post("/hero-carousel", response_model=HeroSlide)
async def create_hero_slide(slide: HeroSlideCreate):
    """Create hero carousel slide"""
    return await crud_public.create_hero_slide(slide)


@router.put("/hero-carousel/{slide_id}", response_model=HeroSlide)
async def update_hero_slide(slide_id: str, slide: HeroSlideUpdate):
    """Update hero carousel slide"""
    updated = await crud_public.update_hero_slide(slide_id, slide)
    if not updated:
        raise NotFoundException("Hero slide", slide_id)
    return updated


@router.delete("/hero-carousel/{slide_id}")
async def delete_hero_slide(slide_id: str):
    """Delete hero carousel slide"""
    success = await crud_public.delete_hero_slide(slide_id)
    if not success:
        raise NotFoundException("Hero slide", slide_id)
    return {"status": "success"}


@router.post("/promo-events", response_model=Promotion)
async def create_promotion(promo: PromotionCreate):
    """Create promotional event"""
    return await crud_public.create_promotion(promo)


@router.put("/promo-events/{promo_id}", response_model=Promotion)
async def update_promotion(promo_id: str, promo: PromotionUpdate):
    """Update promotional event"""
    updated = await crud_public.update_promotion(promo_id, promo)
    if not updated:
        raise NotFoundException("Promotion", promo_id)
    return updated


@router.delete("/promo-events/{promo_id}")
async def delete_promotion(promo_id: str):
    """Delete promotional event"""
    success = await crud_public.delete_promotion(promo_id)
    if not success:
        raise NotFoundException("Promotion", promo_id)
    return {"status": "success"}


# ========== Theatre Management ==========

@router.get("/theatres", response_model=List[Theatre])
async def list_theatres():
    """List all theatres"""
    try:
        theatres = await crud_theatre.get_all()
        return theatres
    except Exception as e:
        logger.error(f"Error fetching theatres: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch theatres"
        )


@router.get("/theatres/{theatre_id}", response_model=Theatre)
async def get_theatre(theatre_id: int):
    """Get theatre details"""
    try:
        theatre = await crud_theatre.get_by_id(theatre_id)
        if not theatre:
            raise NotFoundException("Theatre", theatre_id)
        return theatre
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Error fetching theatre {theatre_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch theatre"
        )


@router.post("/theatres", response_model=Theatre, status_code=201)
async def create_theatre(theatre: TheatreCreate):
    """Create new theatre"""
    try:
        new_theatre = await crud_theatre.create(theatre)
        return new_theatre
    except Exception as e:
        logger.error(f"Error creating theatre: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create theatre"
        )


@router.patch("/theatres/{theatre_id}", response_model=Theatre)
async def update_theatre(theatre_id: int, theatre: TheatreUpdate):
    """Update theatre details"""
    try:
        updated = await crud_theatre.update(theatre_id, theatre)
        if not updated:
            raise NotFoundException("Theatre", theatre_id)
        return updated
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Error updating theatre {theatre_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update theatre"
        )


@router.delete("/theatres/{theatre_id}")
async def delete_theatre(theatre_id: int):
    """Delete theatre"""
    try:
        success = await crud_theatre.delete(theatre_id)
        if not success:
            raise NotFoundException("Theatre", theatre_id)
        return {"status": "success"}
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Error deleting theatre {theatre_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete theatre"
        )


# ========== Seat Management ==========

@router.get("/theatres/{theatre_id}/seats", response_model=List[Seat])
async def list_theatre_seats(theatre_id: int):
    """List all seats for a theatre"""
    try:
        # Verify theatre exists
        theatre = await crud_theatre.get_by_id(theatre_id)
        if not theatre:
            raise NotFoundException("Theatre", theatre_id)

        seats = await crud_seat.get_by_theatre(theatre_id)
        return seats
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Error fetching seats for theatre {theatre_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch seats"
        )


@router.post("/theatres/{theatre_id}/seats", response_model=Seat, status_code=201)
async def create_seat(theatre_id: int, seat: SeatCreate):
    """Create new seat for theatre"""
    try:
        # Verify theatre exists
        theatre = await crud_theatre.get_by_id(theatre_id)
        if not theatre:
            raise NotFoundException("Theatre", theatre_id)

        # Ensure seat's theatre_id matches URL parameter
        seat.theatre_id = theatre_id
        new_seat = await crud_seat.create(seat)
        return new_seat
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Error creating seat for theatre {theatre_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create seat"
        )


@router.patch("/theatres/{theatre_id}/seats/{seat_id}", response_model=Seat)
async def update_seat(theatre_id: int, seat_id: int, seat: SeatUpdate):
    """Update seat status"""
    try:
        # Verify theatre exists
        theatre = await crud_theatre.get_by_id(theatre_id)
        if not theatre:
            raise NotFoundException("Theatre", theatre_id)

        updated = await crud_seat.update(seat_id, seat)
        if not updated:
            raise NotFoundException("Seat", seat_id)
        return updated
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Error updating seat {seat_id} in theatre {theatre_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update seat"
        )


@router.delete("/theatres/{theatre_id}/seats/{seat_id}")
async def delete_seat(theatre_id: int, seat_id: int):
    """Delete seat"""
    try:
        # Verify theatre exists
        theatre = await crud_theatre.get_by_id(theatre_id)
        if not theatre:
            raise NotFoundException("Theatre", theatre_id)

        success = await crud_seat.delete(seat_id)
        if not success:
            raise NotFoundException("Seat", seat_id)
        return {"status": "success"}
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Error deleting seat {seat_id} from theatre {theatre_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete seat"
        )


# ========== Showtime Seat Management ==========

@router.get("/showtimes/{showtime_id}/seats", response_model=List[ShowtimeSeat])
async def list_showtime_seats(showtime_id: int):
    """
    List all seat configurations for a specific showtime.
    Returns which seats are available/blocked for booking in this showtime.
    """
    try:
        # Verify showtime exists
        showtime = await crud_showtime.get_by_id(showtime_id)
        if not showtime:
            raise NotFoundException("Showtime", showtime_id)

        seats = await crud_showtime_seat.get_by_showtime(showtime_id)
        return seats
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Error fetching seats for showtime {showtime_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch showtime seats"
        )


@router.patch("/showtimes/{showtime_id}/seats/batch", response_model=List[ShowtimeSeat])
async def update_showtime_seats_batch(showtime_id: int, seat_configs: dict):
    """
    Batch update seat availability for a showtime.

    Request body: {"seat_id_1": true, "seat_id_2": false, ...}
    where true = available for booking, false = blocked
    """
    try:
        # Verify showtime exists
        showtime = await crud_showtime.get_by_id(showtime_id)
        if not showtime:
            raise NotFoundException("Showtime", showtime_id)

        # Convert string keys to integers
        seat_configs_int = {int(k): v for k, v in seat_configs.items()}

        updated = await crud_showtime_seat.update_batch(showtime_id, seat_configs_int)
        return updated
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Error updating seats for showtime {showtime_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update showtime seats"
        )


@router.patch("/showtime-seats/{showtime_seat_id}", response_model=ShowtimeSeat)
async def update_single_showtime_seat(showtime_seat_id: int, update: ShowtimeSeatUpdate):
    """Update a single showtime seat configuration"""
    try:
        updated = await crud_showtime_seat.update(showtime_seat_id, update)
        if not updated:
            raise NotFoundException("ShowtimeSeat", showtime_seat_id)
        return updated
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Error updating showtime seat {showtime_seat_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update showtime seat"
        )
