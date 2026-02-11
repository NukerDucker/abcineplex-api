from supabase import Client
from typing import List, Optional

class CRUDMovie:
    def __init__(self, supabase_client: Client):
        self.client = supabase_client

    async def get_multi(
        self,
        skip: int = 0,
        limit: int = 20,
        status: Optional[str] = None
    ) -> List[dict]:
        # Start the query with movie_genres joined
        query = self.client.table("movies").select("*, movie_genres(genre_name)")

        # Add optional filters
        if status:
            query = query.eq("release_status", status)

        # Execute with pagination
        response = query.range(skip, skip + limit - 1).execute()

        # Flatten genres
        for movie in response.data:
            if "movie_genres" in movie:
                movie["genres"] = [g["genre_name"] for g in movie["movie_genres"]]
                del movie["movie_genres"]
            else:
                movie["genres"] = []

        return response.data

    async def get_by_id(self, movie_id: int) -> Optional[dict]:
        response = self.client.table("movies")\
            .select("*, movie_genres(genre_name)")\
            .eq("movie_id", movie_id)\
            .single()\
            .execute()
        return response.data