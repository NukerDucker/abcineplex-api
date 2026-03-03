"""
Admin Portal API Routes — Consolidated under /api/v1/admin/
All endpoints require admin privileges.
"""
from fastapi import APIRouter, Query, Depends, HTTPException, status
from typing import Optional, List
from uuid import UUID

from app.crud.movie import CRUDMovie
from app.crud.showtime import CRUDShowtime
from app.crud.booking import CRUDBooking
from app.crud.user import CRUDUser
from app.crud.public import CRUDPublic
from app.crud.theatre import CRUDTheatre, CRUDSeat
from app.schemas.movie import Movie, MovieCreate, MovieUpdate
from app.schemas.showtime import Showtime, ShowtimeCreate, ShowtimeUpdate
from app.schemas.user import AdminUserResponse, AdminUserUpdate
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


# ========== Dashboard ==========

@router.get("/dashboard")
async def get_admin_dashboard(current_user: CurrentUser = Depends(get_admin_user)):
    """Get admin dashboard statistics"""
    try:
        # TODO: Implement dashboard stats aggregation from DB
        # - Total bookings today
        # - Revenue today
        # - Movies now showing count
        # - Upcoming movies count
        # - Total users
        # - Seat fill percentage
        return {
            "total_bookings_today": 0,
            "revenue_today": 0,
            "movies_now_showing": 0,
            "upcoming_movies": 0,
            "total_users": 0,
            "seats_filled_percent": 0.0
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
    """Fetch movie data from TMDB API and return as pre-filled MovieCreate payload."""
    from app.core.config import settings
    import httpx
    from datetime import date as date_type

    if not settings.tmdb_api_key:
        raise HTTPException(status_code=503, detail="TMDB API key not configured")

    url = f"{settings.tmdb_base_url}/movie/{tmdb_id}"
    params = {
        "api_key": settings.tmdb_api_key,
        "append_to_response": "credits,videos",
        "language": "en-US",
    }

    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(url, params=params)
        if resp.status_code == 404:
            raise HTTPException(status_code=404, detail=f"TMDB movie {tmdb_id} not found")
        if resp.status_code != 200:
            raise HTTPException(status_code=502, detail="TMDB API error")
        data = resp.json()

    # Determine release_status from release_date
    release_date_str = data.get("release_date") or ""
    release_status = "upcoming"
    if release_date_str:
        try:
            rd = date_type.fromisoformat(release_date_str)
            release_status = "now_showing" if rd <= date_type.today() else "upcoming"
        except ValueError:
            pass

    # Director and starring from credits
    director = None
    starring: list[str] = []
    if credits := data.get("credits"):
        crew = credits.get("crew") or []
        cast = credits.get("cast") or []
        directors = [c["name"] for c in crew if c.get("job") == "Director"]
        director = directors[0] if directors else None
        starring = [c["name"] for c in cast[:8]]

    # Trailer from videos
    trailer_url = None
    if videos := data.get("videos"):
        for v in (videos.get("results") or []):
            if v.get("site") == "YouTube" and v.get("type") == "Trailer":
                trailer_url = f"https://www.youtube.com/watch?v={v['key']}"
                break

    # Genre
    genres = data.get("genres") or []
    genre_str = ", ".join(g["name"] for g in genres) if genres else None

    # Image URLs
    poster_path = data.get("poster_path")
    backdrop_path = data.get("backdrop_path")
    poster_url = f"{settings.tmdb_image_base_url}{poster_path}" if poster_path else None
    banner_url = f"{settings.tmdb_image_base_url}{backdrop_path}" if backdrop_path else None

    runtime = data.get("runtime") or 0

    return {
        "title": data.get("title", ""),
        "synopsis": data.get("overview"),
        "release_date": release_date_str,
        "runtime_minutes": runtime,
        "duration_minutes": runtime + 15,  # add 15 min for ads
        "credits_duration_minutes": 5,
        "imdb_score": data.get("vote_average"),
        "rating_count": data.get("vote_count"),
        "genre": genre_str,
        "director": director,
        "starring": starring,
        "poster_url": poster_url,
        "banner_url": banner_url,
        "trailer_url": trailer_url,
        "release_status": release_status,
        "content_rating": "",
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
    """Remove a movie listing (soft delete: set status to ended)"""
    # TODO: Implement soft delete logic
    # - Set release_status = 'ended' instead of hard delete
    success = await crud_movie.delete(movie_id)
    if not success:
        raise NotFoundException("Movie", str(movie_id))
    return {"message": "Movie removed"}


# ========== Showtime Management ==========

@router.post("/showtimes", response_model=Showtime, status_code=201)
async def create_admin_showtime(showtime: ShowtimeCreate):
    """Create a new showtime for a movie"""
    try:
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
    # TODO: Implement soft delete logic
    # - Set is_active = false instead of hard delete
    success = await crud_showtime.delete(showtime_id)
    if not success:
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
    """List all bookings with filters"""
    try:
        # TODO: Implement filtered booking list from CRUD
        # - Filter by user_id if provided
        # - Filter by showtime_id if provided
        # - Filter by booking_status if provided
        # - Filter by date if provided
        bookings = await crud_booking.get_all_bookings(booking_status, limit, offset)
        return {"bookings": bookings, "count": len(bookings)}
    except Exception as e:
        logger.error(f"Error fetching bookings: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch bookings"
        )


@router.patch("/bookings/{booking_id}")
async def update_admin_booking(
    booking_id: str,
    new_showtime_id: Optional[int] = Query(None),
    new_seat_ids: Optional[List[int]] = Query(None),
    admin_note: Optional[str] = Query(None)
):
    """Admin changes seat or showtime for a customer booking"""
    try:
        # TODO: Implement admin booking change logic
        # - Validate booking exists
        # - If changing showtime: validate new showtime, check seat availability
        # - If changing seat: validate seats in same showtime
        # - Update booking_seats
        # - Create audit trail
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Endpoint not yet implemented"
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating booking: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update booking"
        )


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
    """Edit customer information including membership and student discount"""
    user_uuid = str(user_id)
    data = user_update.model_dump(exclude_unset=True)
    updated = await crud_user.update(user_uuid, data)
    if not updated:
        raise NotFoundException("User", str(user_id))
    return updated


@router.delete("/users/{user_id}")
async def delete_admin_user(user_id: UUID):
    """Deactivate a user"""
    user_uuid = str(user_id)
    success = await crud_user.deactivate(user_uuid)
    if not success:
        raise NotFoundException("User", str(user_id))
    return {"message": "User deactivated"}


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
