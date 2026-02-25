from supabase import Client
from typing import List, Optional, Dict, Any
from app.schemas.showtime import ShowtimeCreate, ShowtimeUpdate
import logging
import asyncio

logger = logging.getLogger(__name__)


class CRUDShowtime:
    """Optimized showtime CRUD operations"""
    __slots__ = ('client',)

    def __init__(self, supabase_client: Client):
        self.client = supabase_client

    async def create(self, showtime: ShowtimeCreate) -> dict:
        """Create a new showtime"""
        data = showtime.model_dump(mode='json')
        response = await asyncio.to_thread(
            lambda: self.client.table("showtimes").insert(data).execute()
        )
        return response.data[0]

    async def update(self, showtime_id: int, showtime_in: ShowtimeUpdate) -> Optional[dict]:
        """Update showtime with fallback"""
        data = showtime_in.model_dump(exclude_unset=True, mode='json')
        if not data:
            return await self.get_by_id(showtime_id)

        response = await asyncio.to_thread(
            lambda: self.client.table("showtimes")
                .update(data)
                .eq("id", showtime_id)
                .select()
                .maybe_single()
                .execute()
        )
        return response.data

    async def delete(self, showtime_id: int) -> bool:
        """Delete a showtime"""
        response = await asyncio.to_thread(
            lambda: self.client.table("showtimes").delete().eq("id", showtime_id).execute()
        )
        return bool(response.data)

    async def get_by_movie(self, movie_id: int) -> List[dict]:
        """Get all showtimes for a movie"""
        response = await asyncio.to_thread(
            lambda: self.client.table("showtimes")
                .select("*")
                .eq("movie_id", movie_id)
                .order("start_time")
                .execute()
        )
        return response.data or []

    async def get_by_id(self, showtime_id: int) -> Optional[dict]:
        """Get showtime by ID with safe fallback"""
        response = await asyncio.to_thread(
            lambda: self.client.table("showtimes")
                .select("*")
                .eq("id", showtime_id)
                .maybe_single()
                .execute()
        )
        return response.data

    async def get_seats_for_screen(self, screen_id: int, base_price: float) -> List[Dict[str, Any]]:
        """
        Get all seats for a screen with availability status.
        Optimized with single query and list comprehension for memory efficiency.
        """
        response = await asyncio.to_thread(
            lambda: self.client.table("seats")
                .select("id, row_label, seat_number, status")
                .eq("screen_id", screen_id)
                .order("row_label")
                .order("seat_number")
                .execute()
        )

        if not response.data:
            return []

        # Memory-efficient list comprehension instead of loop
        return [
            {
                "seat_id": seat["id"],
                "row_label": seat["row_label"],
                "seat_number": seat["seat_number"],
                "status": seat["status"],
                "price": base_price
            }
            for seat in response.data
        ]

    async def get_detail(self, showtime_id: int) -> Optional[Dict[str, Any]]:
        """Get a showtime with movie and screen joined — for GET /showtimes/:id."""
        response = await asyncio.to_thread(
            lambda: self.client.table("showtimes")
                .select(
                    "*, "
                    "movies(id, title, duration_minutes, imdb_score, rating_count, release_date, credits_duration_minutes), "
                    "screens(id, name, total_seats)"
                )
                .eq("id", showtime_id)
                .maybe_single()
                .execute()
        )
        return response.data

    async def get_seat_map(self, screen_id: int) -> List[Dict[str, Any]]:
        """Get all seats for a screen ordered for seat-map rendering."""
        response = await asyncio.to_thread(
            lambda: self.client.table("seats")
                .select("id, row_label, seat_number, seat_type, status")
                .eq("screen_id", screen_id)
                .order("row_label")
                .order("seat_number")
                .execute()
        )
        return response.data or []

    async def get_screen_occupancy(self, screen_id: int) -> Dict[str, Any]:
        """Get occupancy statistics for a screen with fallback"""
        try:
            response = await asyncio.to_thread(
                lambda: self.client.from_('screen_statistics')
                    .select('*')
                    .eq('screen_id', screen_id)
                    .maybe_single()
                    .execute()
            )

            return response.data or {
                "screen_id": screen_id,
                "total_seats": 0,
                "available_seats": 0,
                "reserved_seats": 0,
                "sold_seats": 0,
                "maintenance_seats": 0
            }
        except Exception as e:
            logger.error(f"Error getting occupancy for screen {screen_id}: {e}")
            # Return default fallback
            return {
                "screen_id": screen_id,
                "total_seats": 0,
                "available_seats": 0,
                "reserved_seats": 0,
                "sold_seats": 0,
                "maintenance_seats": 0
            }
