from fastapi import APIRouter, HTTPException
from typing import List, Dict, Any
from app.crud.showtime import CRUDShowtime
from app.schemas.showtime import Showtime, ShowtimeCreate, ShowtimeUpdate
from app.core.supabase import supabase

router = APIRouter(prefix="/api/showtimes", tags=["showtimes"])
crud_showtime = CRUDShowtime(supabase)

@router.post("", response_model=Showtime)
async def create_showtime(showtime: ShowtimeCreate):
    try:
        return await crud_showtime.create(showtime)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.put("/{showtime_id}", response_model=Showtime)
async def update_showtime(showtime_id: int, showtime: ShowtimeUpdate):
    try:
        updated = await crud_showtime.update(showtime_id, showtime)
        if not updated:
            raise HTTPException(status_code=404, detail="Showtime not found")
        return updated
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.delete("/{showtime_id}")
async def delete_showtime(showtime_id: int):
    try:
        success = await crud_showtime.delete(showtime_id)
        if not success:
            raise HTTPException(status_code=404, detail="Showtime not found")
        return {"status": "success", "message": "Showtime deleted"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/movie/{movie_id}", response_model=List[Showtime])
async def get_showtimes_by_movie(movie_id: int):
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
    """
    Get seat availability and pricing for a specific showtime.
    This endpoint retrieves the screen associated with the showtime,
    then returns all seats for that screen with their current status.
    """
    try:
        showtime = await crud_showtime.get_by_id(showtime_id)
        if not showtime:
            raise HTTPException(
                status_code=404,
                detail=f"Showtime {showtime_id} not found"
            )

        # Get base_price from showtime
        base_price = float(showtime.get('base_price', 15.00))

        # Get screen_id from showtime (should have screen_id field)
        screen_id = showtime.get('screen_id')
        if not screen_id:
            raise HTTPException(
                status_code=400,
                detail="Showtime does not have a screen_id"
            )

        seats = await crud_showtime.get_seats_for_screen(screen_id, base_price)
        if not seats:
            raise HTTPException(
                status_code=404,
                detail=f"No seats found for screen {screen_id}"
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
