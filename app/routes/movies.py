from fastapi import APIRouter, Query
from typing import List, Optional
from app.crud.movie import CRUDMovie
from app.schemas.movie import Movie, MovieCreate, MovieUpdate
from app.core.supabase import supabase
from app.core.exceptions import NotFoundException

router = APIRouter(prefix="/api/movies", tags=["movies"])
crud_movie = CRUDMovie(supabase)


@router.post("", response_model=Movie)
async def create_movie(movie: MovieCreate):
    """Create a new movie"""
    return await crud_movie.create(movie)


@router.put("/{movie_id}", response_model=Movie)
async def update_movie(movie_id: int, movie: MovieUpdate):
    """Update existing movie"""
    updated = await crud_movie.update(movie_id, movie)
    if not updated:
        raise NotFoundException("Movie", str(movie_id))
    return updated


@router.delete("/{movie_id}")
async def delete_movie(movie_id: int):
    """Delete a movie"""
    success = await crud_movie.delete(movie_id)
    if not success:
        raise NotFoundException("Movie", str(movie_id))
    return {"status": "success", "message": "Movie deleted"}


@router.get("/{movie_id}", response_model=Movie)
async def get_movie(movie_id: int):
    """Get movie by ID"""
    movie = await crud_movie.get_by_id(movie_id)
    if not movie:
        raise NotFoundException("Movie", str(movie_id))
    return movie


@router.get("", response_model=List[Movie])
async def get_movies(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    status: Optional[str] = Query(None, description="Filter by release_status")
):
    """
    Get all movies with pagination and optional status filter.
    Global exception handlers manage errors - no need for manual try-catch.
    """
    return await crud_movie.get_multi(skip=skip, limit=limit, status=status)
