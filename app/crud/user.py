from supabase import Client
from typing import List, Optional
import asyncio

class CRUDUser:
    __slots__ = ('client',)

    def __init__(self, supabase_client: Client):
        self.client = supabase_client

    # Standard columns used across all fetch operations
    # Now includes student status, membership, and streaks
    SELECT_COLUMNS = (
        "user_id, email, user_name, full_name, phone, date_of_birth, "
        "loyalty_points, is_admin, is_active, is_student, "
        "student_id_verified, membership_tier, attendance_streak, "
        "created_at, updated_at"
    )

    async def get_multi(self, skip: int = 0, limit: int = 20) -> List[dict]:
        """Return a paginated list of all users for admin management."""
        response = await asyncio.to_thread(
            lambda: self.client.table("users")
                .select(self.SELECT_COLUMNS)
                .order("created_at", desc=True)
                .range(skip, skip + limit - 1)
                .execute()
        )
        return response.data or []

    async def get_by_id(self, user_id: str) -> Optional[dict]:
        """Return a single user by UUID (source of truth for AuthProvider)."""
        response = await asyncio.to_thread(
            lambda: self.client.table("users")
                .select(self.SELECT_COLUMNS)
                .eq("user_id", user_id)
                .maybe_single()
                .execute()
        )
        return response.data if response.data else None

    async def update(self, user_id: str, data: dict) -> Optional[dict]:
        """
        Update fields for a user and return the updated record.
        This handles both UserUpdate and AdminUserUpdate data.
        """
        # Ensure we only try to update if data is provided
        if not data:
            return await self.get_by_id(user_id)

        response = await asyncio.to_thread(
            lambda: self.client.table("users")
                .update(data)
                .eq("user_id", user_id)
                .select(self.SELECT_COLUMNS)
                .maybe_single()
                .execute()
        )
        return response.data if response.data else None

    async def get_by_username(self, user_name: str) -> Optional[dict]:
        """Helper to find a user by their @username."""
        response = await asyncio.to_thread(
            lambda: self.client.table("users")
                .select(self.SELECT_COLUMNS)
                .eq("user_name", user_name)
                .maybe_single()
                .execute()
        )
        return response.data if response.data else None

    async def deactivate(self, user_id: str) -> bool:
        """Soft-delete a user by setting is_active = False."""
        response = await asyncio.to_thread(
            lambda: self.client.table("users")
                .update({"is_active": False})
                .eq("user_id", user_id)
                .execute()
        )
        return bool(response.data)