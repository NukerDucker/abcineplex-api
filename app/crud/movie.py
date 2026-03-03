from supabase import Client
from typing import List, Optional
from app.schemas.movie import MovieCreate, MovieUpdate
import asyncio
import logging

logger = logging.getLogger(__name__)

class CRUDMovie:
    __slots__ = ('client',)

    def __init__(self, supabase_client: Client):
        self.client = supabase_client

    async def create(self, movie: MovieCreate) -> dict:
        data = movie.model_dump(mode='json')
        response = await asyncio.to_thread(
            lambda: self.client.table("movies").insert(data).execute()
        )
        return response.data[0]

    async def update(self, movie_id: int, movie_in: MovieUpdate) -> Optional[dict]:
        data = movie_in.model_dump(exclude_unset=True, mode='json')
        if not data:
            return await self.get_by_id(movie_id)
        response = await asyncio.to_thread(
            lambda: self.client.table("movies")
                .update(data)
                .eq("id", movie_id)
                .execute()
        )
        return response.data[0]

    async def delete(self, movie_id: int) -> bool:
        response = await asyncio.to_thread(
            lambda: self.client.table("movies").delete().eq("id", movie_id).execute()
        )
        return bool(response.data)

    async def get_by_id(self, movie_id: int) -> Optional[dict]:
        response = await asyncio.to_thread(
            lambda: self.client.table("movies")
                .select("*")
                .eq("id", movie_id)
                .maybe_single()
                .execute()
        )
        return response.data

    async def get_multi(
        self,
        page: int = 1,
        limit: int = 20,
        release_status: Optional[str] = None,
        active_only: bool = False,
    ) -> tuple[List[dict], int]:
        offset = (page - 1) * limit

        def _fetch():
            query = self.client.table("movies").select("*", count="exact")
            if release_status:
                query = query.eq("release_status", release_status)
            if active_only:
                query = query.eq("is_active", True)
            return query.range(offset, offset + limit - 1).execute()

        response = await asyncio.to_thread(_fetch)
        return response.data or [], response.count or 0

    async def get_showtimes_for_movie(
        self,
        movie_id: int,
        from_date: str,
        to_date: str,
    ) -> List[dict]:
        """Get showtimes for a movie within [from_date, to_date].

        Joins screens table to get theatre name and seat counts.
        """
        try:
            response = await asyncio.to_thread(
                lambda: self.client.table("showtimes")
                    .select("*, theatres(name, total_seats)")
                    .eq("movie_id", movie_id)
                    .gte("start_time", from_date)
                    .lte("start_time", to_date)
                    .order("start_time")
                    .execute()
            )
            return response.data or []
        except Exception as e:
            logger.error(f"Failed to fetch showtimes for movie {movie_id}: {e}")
            return []
