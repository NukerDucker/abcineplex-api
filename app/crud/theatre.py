from supabase import Client
from typing import List, Optional
from app.schemas.theatre import TheatreCreate, TheatreUpdate, SeatCreate, SeatUpdate
import asyncio
import logging

logger = logging.getLogger(__name__)


class CRUDTheatre:
    __slots__ = ('client',)

    def __init__(self, supabase_client: Client):
        self.client = supabase_client

    async def create(self, theatre: TheatreCreate) -> dict:
        data = theatre.model_dump(mode='json')
        response = await asyncio.to_thread(
            lambda: self.client.table("theatres").insert(data).execute()
        )
        return response.data[0]

    async def update(self, theatre_id: int, theatre_in: TheatreUpdate) -> Optional[dict]:
        data = theatre_in.model_dump(exclude_unset=True, mode='json')
        if not data:
            return await self.get_by_id(theatre_id)
        response = await asyncio.to_thread(
            lambda: self.client.table("theatres")
                .update(data)
                .eq("id", theatre_id)
                .execute()
        )
        return response.data[0] if response.data else None

    async def delete(self, theatre_id: int) -> bool:
        response = await asyncio.to_thread(
            lambda: self.client.table("theatres").delete().eq("id", theatre_id).execute()
        )
        return bool(response.data)

    async def get_by_id(self, theatre_id: int) -> Optional[dict]:
        response = await asyncio.to_thread(
            lambda: self.client.table("theatres")
                .select("*")
                .eq("id", theatre_id)
                .maybe_single()
                .execute()
        )
        return response.data

    async def get_multi(self, skip: int = 0, limit: int = 100) -> List[dict]:
        response = await asyncio.to_thread(
            lambda: self.client.table("theatres")
                .select("*")
                .range(skip, skip + limit - 1)
                .execute()
        )
        return response.data or []

    async def get_all(self) -> List[dict]:
        response = await asyncio.to_thread(
            lambda: self.client.table("theatres")
                .select("*")
                .eq("is_active", True)
                .execute()
        )
        return response.data or []


class CRUDSeat:
    __slots__ = ('client',)

    def __init__(self, supabase_client: Client):
        self.client = supabase_client

    async def create(self, seat: SeatCreate) -> dict:
        data = seat.model_dump(mode='json')
        response = await asyncio.to_thread(
            lambda: self.client.table("seats").insert(data).execute()
        )
        return response.data[0]

    async def update(self, seat_id: int, seat_in: SeatUpdate) -> Optional[dict]:
        data = seat_in.model_dump(exclude_unset=True, mode='json')
        if not data:
            return await self.get_by_id(seat_id)
        response = await asyncio.to_thread(
            lambda: self.client.table("seats")
                .update(data)
                .eq("id", seat_id)
                .execute()
        )
        return response.data[0] if response.data else None

    async def delete(self, seat_id: int) -> bool:
        response = await asyncio.to_thread(
            lambda: self.client.table("seats").delete().eq("id", seat_id).execute()
        )
        return bool(response.data)

    async def get_by_id(self, seat_id: int) -> Optional[dict]:
        response = await asyncio.to_thread(
            lambda: self.client.table("seats")
                .select("*")
                .eq("id", seat_id)
                .maybe_single()
                .execute()
        )
        return response.data

    async def get_by_theatre(self, theatre_id: int) -> List[dict]:
        response = await asyncio.to_thread(
            lambda: self.client.table("seats")
                .select("*")
                .eq("theatre_id", theatre_id)
                .order("row_label")
                .order("seat_number")
                .execute()
        )
        return response.data or []

    async def get_multi(self, skip: int = 0, limit: int = 100) -> List[dict]:
        response = await asyncio.to_thread(
            lambda: self.client.table("seats")
                .select("*")
                .range(skip, skip + limit - 1)
                .execute()
        )
        return response.data or []
