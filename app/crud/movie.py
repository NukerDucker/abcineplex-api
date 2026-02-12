from supabase import Client
from typing import List, Optional, Dict, Any
from app.schemas.movie import MovieCreate, MovieUpdate
import asyncio

class CRUDMovie:
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
            lambda: self.client.table("movies").update(data).eq("id", movie_id).execute()
        )
        if response.data:
            return response.data[0]
        return None

    async def delete(self, movie_id: int) -> bool:
        response = await asyncio.to_thread(
            lambda: self.client.table("movies").delete().eq("id", movie_id).execute()
        )
        # Supabase delete returns the deleted rows. If list is not empty, it was deleted.
        return len(response.data) > 0

    async def get_multi(
        self,
        skip: int = 0,
        limit: int = 20,
        status: Optional[str] = None
    ) -> List[dict]:
        def _fetch():
            # Start the query with movie_genres joined
            query = self.client.table("movies").select("*")

            # Add optional filters
            if status:
                db_status = status
                if status == "NOW_SCREENING":
                    db_status = "now_showing"
                elif status == "COMING_SOON":
                    db_status = "coming_soon"
                query = query.eq("release_status", db_status)

            # Execute with pagination
            return query.range(skip, skip + limit - 1).execute()

        response = await asyncio.to_thread(_fetch)

        # Flatten genres
        for movie in response.data:
            if "movie_genres" in movie:
                movie["genres"] = [g["genre_name"] for g in movie["movie_genres"]]
                del movie["movie_genres"]
            else:
                movie["genres"] = []

        return response.data

    async def get_by_id(self, movie_id: int) -> Optional[dict]:
        response = await asyncio.to_thread(
            lambda: self.client.table("movies")
                .select("*")
                .eq("id", movie_id)
                .single()
                .execute()
        )
        return response.data