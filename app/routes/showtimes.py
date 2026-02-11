from fastapi import APIRouter, HTTPException
from typing import List, Dict, Any
from app.crud.showtime import CRUDShowtime
from app.schemas.showtime import Showtime
from app.core.supabase import supabase

router = APIRouter(prefix="/api/showtimes", tags=["showtimes"])
crud_showtime = CRUDShowtime(supabase)


@router.get("/movie/{movie_id}", response_model=List[Showtime])
async def get_showtimes_by_movie(movie_id: int):
    """Get all showtimes for a specific movie"""
    try:
        showtimes = await crud_showtime.get_by_movie(movie_id)
        if not showtimes:
            raise HTTPException(
                status_code=404,
                detail=f"No showtimes found for movie {movie_id}"
            )
        return showtimes
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching showtimes: {str(e)}")


@router.get("/{showtime_id}/seats", response_model=List[Dict[str, Any]])
async def get_showtime_seats(showtime_id: int):
    """Get seat availability and pricing for a specific showtime"""
    try:
        seats = await crud_showtime.get_seats(showtime_id)
        if not seats:
            raise HTTPException(
                status_code=404,
                detail=f"No seats found for showtime {showtime_id}"
            )
        return seats
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching seats: {str(e)}")


@router.get("/{showtime_id}", response_model=Showtime)
async def get_showtime(showtime_id: int):
    """Get details of a specific showtime"""
    try:
        showtime = await crud_showtime.get_by_id(showtime_id)
        if not showtime:
            raise HTTPException(
                status_code=404,
                detail=f"Showtime {showtime_id} not found"
            )
        return showtime
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching showtime: {str(e)}")
