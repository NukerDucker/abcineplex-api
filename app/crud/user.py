from supabase import Client
from typing import List, Optional
from app.core.exceptions import UnauthorizedException
import asyncio


class CRUDUser:
    """Optimized user CRUD operations with minimal memory footprint"""
    __slots__ = ('client',)

    def __init__(self, supabase_client: Client):
        self.client = supabase_client

    async def get_multi(
        self,
        skip: int = 0,
        limit: int = 20,
        is_admin: bool = False
    ) -> List[dict]:
        """Get multiple users - admin only"""
        if not is_admin:
            raise UnauthorizedException()

        response = await asyncio.to_thread(
            lambda: self.client.table("users")
                .select("user_id, email, user_name, full_name, phone, loyalty_points, created_at, updated_at")
                .order("created_at", desc=True)
                .range(skip, skip + limit - 1)
                .execute()
        )
        return response.data if response and hasattr(response, 'data') else []

    async def get_by_id(
        self,
        user_id: str,
        current_user_id: str,
        is_admin: bool = False
    ) -> Optional[dict]:
        """Get user by ID with authorization check"""
        if not is_admin and user_id != current_user_id:
            raise UnauthorizedException()

        try:
            response = await asyncio.to_thread(
                lambda: self.client.table("users")
                    .select("*")
                    .eq("user_id", user_id)
                    .maybe_single()
                    .execute()
            )
            if response and hasattr(response, 'data'):
                return response.data
            return None
        except Exception as e:
            print(f"Error fetching user {user_id}: {e}")
            return None

    async def get_by_email(self, email: str) -> Optional[dict]:
        """Get user by email - optimized with maybe_single"""
        try:
            response = await asyncio.to_thread(
                lambda: self.client.table("users")
                    .select("*")
                    .eq("email", email)
                    .maybe_single()
                    .execute()
            )
            return response.data if response and hasattr(response, 'data') else None
        except Exception as e:
            print(f"Error fetching user by email {email}: {e}")
            return None

    async def update(
        self,
        user_id: str,
        user_in: dict,
        current_user_id: str,
        is_admin: bool = False
    ) -> Optional[dict]:
        """Update user with safe field filtering"""
        if not is_admin and user_id != current_user_id:
            raise UnauthorizedException()

        # Only allow safe fields for non-admin users
        allowed_fields = {"full_name", "phone", "user_name"} if not is_admin else None
        safe_data = {k: v for k, v in user_in.items() if allowed_fields is None or k in allowed_fields}

        if not safe_data:
            return await self.get_by_id(user_id, current_user_id, is_admin)

        response = await asyncio.to_thread(
            lambda: self.client.table("users")
                .update(safe_data)
                .eq("user_id", user_id)
                .select()
                .maybe_single()
                .execute()
        )

        return response.data if response and hasattr(response, 'data') else None

    async def delete(
        self,
        user_id: str,
        current_user_id: str,
        is_admin: bool = False
    ) -> bool:
        """Soft delete user"""
        if not is_admin and user_id != current_user_id:
            raise UnauthorizedException()

        response = await asyncio.to_thread(
            lambda: self.client.table("users")
                .update({"is_active": False})
                .eq("user_id", user_id)
                .execute()
        )

        return bool(response and hasattr(response, 'data') and response.data)