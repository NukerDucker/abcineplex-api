"""CRUD operations for showtime seat configurations"""
from typing import List, Optional
from supabase import Client
from app.schemas.showtime_seat import ShowtimeSeat, ShowtimeSeatCreate, ShowtimeSeatUpdate
import asyncio
import logging

logger = logging.getLogger(__name__)


class CRUDShowtimeSeat:
    __slots__ = ('client', 'table')

    def __init__(self, supabase_client: Client):
        self.client = supabase_client
        self.table = "showtime_seats"

    async def get_by_showtime(self, showtime_id: int) -> List[ShowtimeSeat]:
        """Get all seat configurations for a specific showtime"""
        response = await asyncio.to_thread(
            lambda: self.client.from_(self.table).select("*").eq("showtime_id", showtime_id).execute()
        )
        return [ShowtimeSeat(**row) for row in response.data] if response.data else []

    async def get_by_id(self, showtime_seat_id: int) -> Optional[ShowtimeSeat]:
        """Get a specific showtime seat configuration"""
        response = await asyncio.to_thread(
            lambda: self.client.from_(self.table).select("*").eq("id", showtime_seat_id).single().execute()
        )
        return ShowtimeSeat(**response.data) if response.data else None

    async def create_bulk(self, showtime_id: int, seat_ids: List[int]) -> List[ShowtimeSeat]:
        """Create showtime seat configs for all seats in a theatre when showtime is created"""
        data = [
            {"showtime_id": showtime_id, "seat_id": seat_id, "is_available": True}
            for seat_id in seat_ids
        ]
        if not data:
            return []
        response = await asyncio.to_thread(
            lambda: self.client.from_(self.table).insert(data).execute()
        )
        return [ShowtimeSeat(**row) for row in response.data] if response.data else []

    async def update(self, showtime_seat_id: int, update_data: ShowtimeSeatUpdate) -> Optional[ShowtimeSeat]:
        """Update a showtime seat configuration"""
        response = await asyncio.to_thread(
            lambda: self.client.from_(self.table).update(update_data.model_dump()).eq("id", showtime_seat_id).execute()
        )
        return ShowtimeSeat(**response.data[0]) if response.data else None

    async def update_batch(self, showtime_id: int, seat_configs: dict) -> List[ShowtimeSeat]:
        """
        Batch update seat availability for a showtime.

        Args:
            showtime_id: The showtime ID
            seat_configs: Dict mapping {seat_id: is_available}
        """
        results = []
        for seat_id, is_available in seat_configs.items():
            response = await asyncio.to_thread(
                lambda sid=seat_id, ia=is_available: self.client.from_(self.table).update(
                    {"is_available": ia}
                ).eq("showtime_id", showtime_id).eq("seat_id", sid).execute()
            )
            if response.data:
                results.append(ShowtimeSeat(**response.data[0]))
        return results

    async def delete(self, showtime_seat_id: int) -> bool:
        """Delete a showtime seat configuration"""
        response = await asyncio.to_thread(
            lambda: self.client.from_(self.table).delete().eq("id", showtime_seat_id).execute()
        )
        return bool(response.data)

    async def delete_by_showtime(self, showtime_id: int) -> int:
        """Delete all seat configurations for a showtime (when showtime is deleted)"""
        response = await asyncio.to_thread(
            lambda: self.client.from_(self.table).delete().eq("showtime_id", showtime_id).execute()
        )
        return len(response.data) if response.data else 0
