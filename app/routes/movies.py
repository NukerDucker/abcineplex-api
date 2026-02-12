from fastapi import APIRouter, Query, HTTPException
from typing import List, Optional
from app.crud.movie import CRUDMovie
from app.schemas.movie import Movie, MovieCreate, MovieUpdate
from app.core.supabase import supabase

router = APIRouter(prefix="/api/movies", tags=["movies"])
crud_movie = CRUDMovie(supabase)

@router.post("", response_model=Movie)
async def create_movie(movie: MovieCreate):
    try:
        return await crud_movie.create(movie)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.put("/{movie_id}", response_model=Movie)
async def update_movie(movie_id: int, movie: MovieUpdate):
    try:
        updated = await crud_movie.update(movie_id, movie)
        if not updated:
            raise HTTPException(status_code=404, detail="Movie not found")
        return updated
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.delete("/{movie_id}")
async def delete_movie(movie_id: int):
    try:
        success = await crud_movie.delete(movie_id)
        if not success:
            raise HTTPException(status_code=404, detail="Movie not found")
        return {"status": "success", "message": "Movie deleted"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/{movie_id}", response_model=Movie)
async def get_movie(movie_id: int):
    movie = await crud_movie.get_by_id(movie_id)
    if not movie:
        raise HTTPException(status_code=404, detail="Movie not found")
    return movie

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
