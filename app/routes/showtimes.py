from fastapi import APIRouter, Depends
from typing import List, Dict, Any
from app.crud.showtime import CRUDShowtime
from app.schemas.showtime import Showtime, ShowtimeCreate, ShowtimeUpdate
from app.core.supabase import supabase
from app.core.exceptions import NotFoundException
from app.core.security import get_admin_user

router = APIRouter(prefix="/api/showtimes", tags=["showtimes"])
crud_showtime = CRUDShowtime(supabase)


@router.post("", response_model=Showtime)
async def create_showtime(showtime: ShowtimeCreate, _admin: object = Depends(get_admin_user)):
    """Create new showtime - Admin only"""
    return await crud_showtime.create(showtime)


@router.put("/{showtime_id}", response_model=Showtime)
async def update_showtime(showtime_id: int, showtime: ShowtimeUpdate, _admin: object = Depends(get_admin_user)):
    """Update showtime - Admin only"""
    updated = await crud_showtime.update(showtime_id, showtime)
    if not updated:
        raise NotFoundException("Showtime", str(showtime_id))
    return updated


@router.delete("/{showtime_id}")
async def delete_showtime(showtime_id: int, _admin: object = Depends(get_admin_user)):
    """Delete showtime - Admin only"""
    success = await crud_showtime.delete(showtime_id)
    if not success:
        raise NotFoundException("Showtime", str(showtime_id))
    return {"status": "success", "message": "Showtime deleted"}


@router.get("/movie/{movie_id}", response_model=List[Showtime])
async def get_showtimes_by_movie(movie_id: int):
    """Get all showtimes for a movie"""
    showtimes = await crud_showtime.get_by_movie(movie_id)
    if not showtimes:
        raise NotFoundException("Showtimes for movie", str(movie_id))
    return showtimes


@router.get("/{showtime_id}/seats", response_model=List[Dict[str, Any]])
async def get_showtime_seats(showtime_id: int):
    """Get seat availability and pricing for a showtime"""
    showtime = await crud_showtime.get_by_id(showtime_id)
    if not showtime:
        raise NotFoundException("Showtime", str(showtime_id))

    base_price = float(showtime.get('base_price', 15.00))
    screen_id = showtime.get('screen_id')

    if not screen_id:
        raise NotFoundException("Screen for showtime", str(showtime_id))

    seats = await crud_showtime.get_seats_for_screen(screen_id, base_price)
    if not seats:
        raise NotFoundException(f"Seats for screen", str(screen_id))

    return seats


@router.get("/{showtime_id}", response_model=Showtime)
async def get_showtime(showtime_id: int):
    """Get showtime details"""
    showtime = await crud_showtime.get_by_id(showtime_id)
    if not showtime:
        raise NotFoundException("Showtime", str(showtime_id))
    return showtime
