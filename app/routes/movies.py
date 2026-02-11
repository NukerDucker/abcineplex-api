from fastapi import APIRouter, Query, HTTPException
from typing import List, Optional
from app.crud.movie import CRUDMovie
from app.schemas.movie import Movie
from app.core.supabase import supabase

router = APIRouter(prefix="/api/movies", tags=["movies"])
crud_movie = CRUDMovie(supabase)


@router.get("", response_model=List[Movie])
async def get_movies(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    status: Optional[str] = Query(None)
):
    """
    Get all movies with pagination

    - **skip**: Number of movies to skip (default: 0)
    - **limit**: Number of movies to return (default: 20, max: 100)
    - **status**: Filter by release_status (e.g., 'NOW_SCREENING', 'COMING_SOON')
    """
    try:
        movies = await crud_movie.get_multi(skip=skip, limit=limit, status=status)
        return movies
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching movies: {str(e)}")


@router.get("/{movie_id}", response_model=Movie)
async def get_movie(movie_id: int):
    """Get a single movie by ID with full details"""
    try:
        movie = await crud_movie.get_by_id(movie_id)
        if not movie:
            raise HTTPException(status_code=404, detail=f"Movie with ID {movie_id} not found")
        return movie
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching movie: {str(e)}")
