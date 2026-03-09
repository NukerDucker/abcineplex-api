from supabase import Client
from typing import List, Optional
import asyncio
import logging

logger = logging.getLogger(__name__)

class CRUDUser:
    __slots__ = ('client',)

    def __init__(self, supabase_client: Client):
        self.client = supabase_client

    # Standard columns used across all fetch operations
    # Keep in sync with the public.users table definition
    SELECT_COLUMNS = (
        "id, email, user_name, full_name, phone, date_of_birth, "
        "loyalty_points, is_admin, is_active, is_student, "
        "student_id_verified, has_password, "
        "membership_tier, attendance_streak, "
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
        try:
            response = await asyncio.to_thread(
                lambda: self.client.table("users")
                    .select('*')
                    .eq("id", user_id)
                    .maybe_single()
                    .execute()
            )
            if response and response.data and isinstance(response.data, dict):
                return response.data
            return None
        except Exception as exc:
            # Handle 204 No Content or other errors gracefully
            logger.warning("get_by_id failed for user %s: %s", user_id, exc)
            return None

    async def update(self, user_id: str, data: dict) -> Optional[dict]:
        """
        Update fields for a user and return the updated record.
        This handles both UserUpdate and AdminUserUpdate data.
        """
        # Ensure we only try to update if data is provided
        if not data:
            return await self.get_by_id(user_id)

        try:
            response = await asyncio.to_thread(
                lambda: self.client.table("users")
                    .update(data)
                    .eq("id", user_id)
                    .select(self.SELECT_COLUMNS)
                    .maybe_single()
                    .execute()
            )
            if response and response.data and isinstance(response.data, dict):
                return response.data
            # UPDATE may have succeeded but the SELECT-after-update returned
            # nothing (e.g. RLS blocks the return-select on the service client
            # in some Supabase configurations). Fall back to a plain GET.
            logger.debug(
                "update for user %s returned no row from select; falling back to get_by_id",
                user_id,
            )
            return await self.get_by_id(user_id)
        except Exception as exc:
            logger.error("update failed for user %s: %s", user_id, exc)
            raise

    async def get_by_username(self, user_name: str) -> Optional[dict]:
        """Helper to find a user by their @username."""
        try:
            response = await asyncio.to_thread(
                lambda: self.client.table("users")
                    .select(self.SELECT_COLUMNS)
                    .eq("user_name", user_name)
                    .maybe_single()
                    .execute()
            )
            if response and response.data and isinstance(response.data, dict):
                return response.data
            return None
        except Exception:
            # Handle 204 No Content or other errors gracefully
            return None

    async def deactivate(self, user_id: str) -> bool:
        """Soft-delete a user by setting is_active = False."""
        try:
            response = await asyncio.to_thread(
                lambda: self.client.table("users")
                    .update({"is_active": False})
                    .eq("id", user_id)
                    .execute()
            )
            return bool(response.data)
        except Exception:
            # Handle errors gracefully
            return False