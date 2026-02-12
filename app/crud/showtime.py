from supabase import Client
from typing import List, Optional, Dict, Any
from datetime import datetime
from app.schemas.showtime import ShowtimeCreate, ShowtimeUpdate
import logging
import asyncio

logger = logging.getLogger(__name__)


class CRUDShowtime:
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
        """Update a showtime"""
        data = showtime_in.model_dump(exclude_unset=True, mode='json')
        if not data:
            return await self.get_by_id(showtime_id)

        response = await asyncio.to_thread(
            lambda: self.client.table("showtimes").update(data).eq("id", showtime_id).execute()
        )
        if response.data:
            return response.data[0]
        return None

    async def delete(self, showtime_id: int) -> bool:
        """Delete a showtime"""
        response = await asyncio.to_thread(
            lambda: self.client.table("showtimes").delete().eq("id", showtime_id).execute()
        )
        return len(response.data) > 0

    async def get_by_movie(self, movie_id: int) -> List[dict]:
        """Get all showtimes for a movie"""
        response = await asyncio.to_thread(
            lambda: self.client.table("showtimes")
                .select("*")
                .eq("movie_id", movie_id)
                .order("start_time")
                .execute()
        )
        return response.data

    async def get_by_id(self, showtime_id: int) -> Optional[dict]:
        """Get a showtime by ID"""
        response = await asyncio.to_thread(
            lambda: self.client.table("showtimes")
                .select("*")
                .eq("id", showtime_id)
                .single()
                .execute()
        )
        return response.data

    async def get_seats_for_screen(self, screen_id: int, base_price: float) -> List[Dict[str, Any]]:
        """
        Get all seats for a screen with their availability status.
        This is used for showing seat maps in the booking UI.

        Seat statuses:
        - "available": Not booked
        - "reserved": Temporarily locked (pending payment)
        - "sold": Sold/booked
        - "maintenance": Out of service
        """
        try:
            # Get all seats for this screen
            seats_response = await asyncio.to_thread(
                lambda: self.client.table("seats")
                    .select("*")
                    .eq("screen_id", screen_id)
                    .order("row_label")
                    .order("seat_number")
                    .execute()
            )

            if not seats_response.data:
                return []

            # Format the response
            results = []
            for seat in seats_response.data:
                results.append({
                    "seat_id": seat["id"],
                    "row_label": seat["row_label"],
                    "seat_number": seat["seat_number"],
                    "status": seat["status"],
                    "price": base_price
                })

            return results
        except Exception as e:
            logger.error(f"Error getting seats for screen {screen_id}: {e}")
            raise

    async def get_screen_occupancy(self, screen_id: int) -> Dict[str, Any]:
        """
        Get occupancy statistics for a screen.
        """
        try:
            response = self.client.from_('screen_statistics')\
                .select('*')\
                .eq('screen_id', screen_id)\
                .single()\
                .execute()

            if response.data:
                return response.data
            return {
                "screen_id": screen_id,
                "total_seats": 0,
                "available_seats": 0,
                "reserved_seats": 0,
                "sold_seats": 0,
                "maintenance_seats": 0
            }
        except Exception as e:
            logger.error(f"Error getting occupancy for screen {screen_id}: {e}")
            raise
