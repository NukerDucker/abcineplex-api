from supabase import Client
from typing import List, Optional
import asyncio

class CRUDReview:
    __slots__ = ('client',)

    def __init__(self, supabase_client: Client):
        self.client = supabase_client

    def _enrich_with_movie(self, review: dict) -> dict:
        """Pull movies sub-object up into a 'movie' key."""
        movies_data = review.pop('movies', None)
        if movies_data and isinstance(movies_data, dict):
            review['movie'] = movies_data
        else:
            review['movie'] = None
        return review

    async def get_by_movie(self, movie_id: int, skip: int = 0, limit: int = 20) -> dict:
        """Get reviews for a movie with total count"""
        def fetch_data():
            count_res = self.client.table("movie_reviews") \
                .select("id", count="exact") \
                .eq("movie_id", movie_id) \
                .execute()

            reviews_res = self.client.table("movie_reviews") \
                .select("*") \
                .eq("movie_id", movie_id) \
                .order("created_at", desc=True) \
                .range(skip, skip + limit - 1) \
                .execute()

            return count_res.count or 0, reviews_res.data or []

        total, items = await asyncio.to_thread(fetch_data)
        return {"total": total, "items": items}

    async def get_latest(self, limit: int = 20, user_id: Optional[str] = None) -> dict:
        """Get latest reviews across all movies, enriched with movie info"""
        def fetch():
            res = self.client.table("movie_reviews") \
                .select("*, movies!inner(id, title, poster_url, release_date)") \
                .order("created_at", desc=True) \
                .limit(limit) \
                .execute()
            rows = res.data or []
            if user_id and rows:
                liked_res = self.client.table("review_likes") \
                    .select("review_id") \
                    .eq("user_id", user_id) \
                    .in_("review_id", [r["id"] for r in rows]) \
                    .execute()
                liked_set = {l["review_id"] for l in (liked_res.data or [])}
            else:
                liked_set = set()
            result = []
            for r in rows:
                r = self._enrich_with_movie(dict(r))
                r["user_liked"] = r["id"] in liked_set
                result.append(r)
            return result

        items = await asyncio.to_thread(fetch)
        return {"total": len(items), "items": items}

    async def get_by_user(self, user_id: str, limit: int = 50) -> dict:
        """Get all reviews written by a specific user, enriched with movie info"""
        def fetch():
            res = self.client.table("movie_reviews") \
                .select("*, movies!inner(id, title, poster_url, release_date)") \
                .eq("user_id", user_id) \
                .order("created_at", desc=True) \
                .limit(limit) \
                .execute()
            rows = res.data or []
            return [self._enrich_with_movie(dict(r)) for r in rows]

        items = await asyncio.to_thread(fetch)
        return {"total": len(items), "items": items}

    async def create(self, review_in: dict, user_id: str) -> dict:
        """Create new review — one per user per movie (enforced by DB unique constraint)"""
        def validate_and_create():
            try:
                insert_res = self.client.table("movie_reviews").insert(review_in).execute()
            except Exception as exc:
                # Postgres unique-violation code 23505 → user already reviewed this movie
                if "23505" in str(exc):
                    raise ValueError("DUPLICATE_REVIEW")
                raise
            if not insert_res.data:
                raise ValueError("Create failed")
            return insert_res.data[0]

        return await asyncio.to_thread(validate_and_create)

    async def update(self, review_id: int, review_in: dict, user_id: str) -> Optional[dict]:
        """Update review text or rating if owned by user"""
        response = await asyncio.to_thread(
            lambda: self.client.table("movie_reviews")
                .update(review_in)
                .eq("id", review_id)
                .eq("user_id", user_id)
                .select()
                .maybe_single()
                .execute()
        )
        return response.data

    async def delete(self, review_id: int, user_id: str) -> bool:
        """Delete review if owned by user"""
        response = await asyncio.to_thread(
            lambda: self.client.table("movie_reviews")
                .delete()
                .eq("id", review_id)
                .eq("user_id", user_id)
                .execute()
        )
        return bool(response.data)

    async def add_like(self, review_id: int, user_id: str) -> dict:
        """Add a like to a review and increment like_count"""
        def process_like():
            like_res = self.client.table("review_likes").insert({
                "review_id": review_id,
                "user_id": user_id
            }).execute()

            if not like_res.data:
                raise ValueError("Already liked or failed")

            review = self.client.table("movie_reviews").select("like_count, user_id").eq("id", review_id).single().execute()
            new_count = (review.data.get("like_count") or 0) + 1
            self.client.table("movie_reviews").update({"like_count": new_count}).eq("id", review_id).execute()

            return like_res.data[0]

        try:
            return await asyncio.to_thread(process_like)
        except Exception as e:
            if "duplicate key" in str(e).lower():
                raise ValueError("Already liked")
            raise e

    async def remove_like(self, review_id: int, user_id: str) -> bool:
        """Remove a like from a review and decrement like_count"""
        def process_unlike():
            unlike_res = self.client.table("review_likes") \
                .delete() \
                .eq("review_id", review_id) \
                .eq("user_id", user_id) \
                .execute()

            if not unlike_res.data:
                return False

            review = self.client.table("movie_reviews").select("like_count").eq("id", review_id).single().execute()
            new_count = max(0, (review.data.get("like_count") or 0) - 1)
            self.client.table("movie_reviews").update({"like_count": new_count}).eq("id", review_id).execute()

            return True

        return await asyncio.to_thread(process_unlike)
