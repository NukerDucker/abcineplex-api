from supabase import Client
from typing import List, Optional
from app.schemas.movie import MovieCreate, MovieUpdate
import asyncio


class CRUDMovie:
    """Optimized movie CRUD with memory-efficient operations"""
    __slots__ = ('client',)

    def __init__(self, supabase_client: Client):
        self.client = supabase_client

    async def create(self, movie: MovieCreate) -> dict:
        """Create new movie, returns created record"""
        data = movie.model_dump(mode='json')
        response = await asyncio.to_thread(
            lambda: self.client.table("movies").insert(data).select().execute()
        )
        return response.data[0]

    async def update(self, movie_id: int, movie_in: MovieUpdate) -> Optional[dict]:
        """Update movie, returns updated record or existing if no changes"""
        data = movie_in.model_dump(exclude_unset=True, mode='json')
        if not data:
            return await self.get_by_id(movie_id)

        response = await asyncio.to_thread(
            lambda: self.client.table("movies")
                .update(data)
                .eq("id", movie_id)
                .select()
                .maybe_single()
                .execute()
        )
        return response.data

    async def delete(self, movie_id: int) -> bool:
        """Delete movie, returns success status"""
        response = await asyncio.to_thread(
            lambda: self.client.table("movies").delete().eq("id", movie_id).execute()
        )
        return bool(response.data)

    async def get_multi(
        self,
        skip: int = 0,
        limit: int = 20,
        status: Optional[str] = None
    ) -> List[dict]:
        """Get movies with optional status filter"""
        def _fetch():
            query = self.client.table("movies").select("*")
            if status:
                query = query.eq("release_status", status)
            return query.range(skip, skip + limit - 1).execute()

        response = await asyncio.to_thread(_fetch)
        return response.data or []

    async def get_by_id(self, movie_id: int) -> Optional[dict]:
        """Get movie by ID with safe fallback"""
        response = await asyncio.to_thread(
            lambda: self.client.table("movies")
                .select("*")
                .eq("id", movie_id)
                .maybe_single()
                .execute()
        )
        return response.data