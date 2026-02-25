from supabase import Client
from typing import List, Optional
import asyncio


class CRUDUser:
    __slots__ = ('client',)

    def __init__(self, supabase_client: Client):
        self.client = supabase_client

    async def get_multi(self, skip: int = 0, limit: int = 20) -> List[dict]:
        """Return a paginated list of all users."""
        response = await asyncio.to_thread(
            lambda: self.client.table("users")
                .select("user_id, email, user_name, full_name, phone, loyalty_points, is_admin, is_active, created_at, updated_at")
                .order("created_at", desc=True)
                .range(skip, skip + limit - 1)
                .execute()
        )
        return response.data or []

    async def get_by_id(self, user_id: str) -> Optional[dict]:
        """Return a single user by UUID."""
        response = await asyncio.to_thread(
            lambda: self.client.table("users")
                .select("user_id, email, user_name, full_name, phone, loyalty_points, is_admin, is_active, created_at, updated_at")
                .eq("user_id", user_id)
                .maybe_single()
                .execute()
        )
        return response.data if response else None

    async def update(self, user_id: str, data: dict) -> Optional[dict]:
        """Update allowed fields for a user and return the updated record."""
        response = await asyncio.to_thread(
            lambda: self.client.table("users")
                .update(data)
                .eq("user_id", user_id)
                .select("user_id, email, user_name, full_name, phone, loyalty_points, is_admin, is_active, created_at, updated_at")
                .maybe_single()
                .execute()
        )
        return response.data if response else None

    async def deactivate(self, user_id: str) -> bool:
        """Soft-delete a user by setting is_active = False."""
        response = await asyncio.to_thread(
            lambda: self.client.table("users")
                .update({"is_active": False})
                .eq("user_id", user_id)
                .execute()
        )
        return bool(response and response.data)
