from supabase import Client
from typing import List, Optional
import asyncio

class CRUDReview:
    __slots__ = ('client',)

    def __init__(self, supabase_client: Client):
        self.client = supabase_client

    async def get_by_movie(self, movie_id: int, skip: int = 0, limit: int = 20) -> dict:
        """Get reviews for a movie with total count"""
        def fetch_data():
            count_res = self.client.table("reviews") \
                .select("id", count="exact") \
                .eq("movie_id", movie_id) \
                .execute()

            reviews_res = self.client.table("reviews") \
                .select("*") \
                .eq("movie_id", movie_id) \
                .order("created_at", desc=True) \
                .range(skip, skip + limit - 1) \
                .execute()

            return count_res.count or 0, reviews_res.data or []

        total, items = await asyncio.to_thread(fetch_data)

        return {
            "total": total,
            "items": items
        }

    async def create(self, review_in: dict, user_id: str) -> dict:
        """Create new review with booking validation"""
        booking_id = review_in.get('booking_id')
        movie_id = review_in.get('movie_id')

        # Validate booking exists and belongs to user
        def validate_and_create():
            # Query booking with its showtime info
            booking_res = self.client.table('bookings') \
                .select('id, user_id, status, showtime_id') \
                .eq('id', booking_id) \
                .eq('user_id', user_id) \
                .maybe_single() \
                .execute()

            if not booking_res.data:
                raise ValueError("Booking not found or does not belong to you")

            booking = booking_res.data
            if booking.get('status') != 'confirmed':
                raise ValueError("You can only review movies from confirmed bookings")

            # Verify the showtime's movie matches the review's movie_id
            showtime_res = self.client.table('showtimes') \
                .select('movie_id') \
                .eq('id', booking.get('showtime_id')) \
                .maybe_single() \
                .execute()

            if not showtime_res.data or showtime_res.data.get('movie_id') != movie_id:
                raise ValueError("The movie in your booking does not match the movie being reviewed")

            # All validations passed, insert review
            insert_res = self.client.table("reviews").insert(review_in).execute()
            if not insert_res.data:
                raise ValueError("Create failed")
            return insert_res.data[0]

        return await asyncio.to_thread(validate_and_create)

    async def update(self, review_id: int, review_in: dict, user_id: str) -> Optional[dict]:
        """Update review text or rating if owned by user"""
        response = await asyncio.to_thread(
            lambda: self.client.table("reviews")
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
            lambda: self.client.table("reviews")
                .delete()
                .eq("id", review_id)
                .eq("user_id", user_id)
                .execute()
        )
        return bool(response.data)

    async def add_like(self, review_id: int, user_id: str) -> dict:
        """Add a like to a review and increment like_count"""
        def process_like():
            # Add to review_likes table
            like_res = self.client.table("review_likes").insert({
                "review_id": review_id,
                "user_id": user_id
            }).select().execute()

            if not like_res.data:
                raise ValueError("Already liked or failed")

            review = self.client.table("reviews").select("like_count").eq("id", review_id).single().execute()
            new_count = (review.data.get("like_count") or 0) + 1
            self.client.table("reviews").update({"like_count": new_count}).eq("id", review_id).execute()

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

            review = self.client.table("reviews").select("like_count").eq("id", review_id).single().execute()
            new_count = max(0, (review.data.get("like_count") or 0) - 1)
            self.client.table("reviews").update({"like_count": new_count}).eq("id", review_id).execute()

            return True

        return await asyncio.to_thread(process_unlike)
