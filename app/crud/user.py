from supabase import Client
from typing import List, Optional
import asyncio

# Constants for error messages
ERROR_NOT_AUTHORIZED = "Not authorized"


class CRUDUser:
    def __init__(self, supabase_client: Client):
        self.client = supabase_client

    async def get_multi(
        self,
        skip: int = 0,
        limit: int = 20,
        is_admin: bool = False
    ) -> List[dict]:
        if not is_admin:
            raise ValueError(ERROR_NOT_AUTHORIZED)

        response = await asyncio.to_thread(
            lambda: self.client.table("users")
                .select("user_id, email, user_name, full_name, phone, loyalty_points, created_at, updated_at")
                .order("created_at", desc=True)
                .range(skip, skip + limit - 1)
                .execute()
        )
        return response.data

    async def get_by_id(
        self,
        user_id: str, # Changed from int to str (UUID)
        current_user_id: str,
        is_admin: bool = False
    ) -> Optional[dict]:
        if not is_admin and user_id != current_user_id:
            raise ValueError(ERROR_NOT_AUTHORIZED)

        response = await asyncio.to_thread(
            lambda: self.client.table("users")
                .select("*")
                .eq("user_id", user_id)
                .execute()
        )

        return response.data[0] if response.data else None

    async def get_by_email(
        self,
        email: str,
    ) -> Optional[dict]:
        response = await asyncio.to_thread(
            lambda: self.client.table("users")
                .select("*")
                .eq("email", email)
                .execute()
        )

        return response.data[0] if response.data else None

    async def get_me(self) -> Optional[dict]:
        """Fetches the profile of the currently logged-in user."""
        auth_user = await asyncio.to_thread(lambda: self.client.auth.get_user())
        if not auth_user.user:
            return None

        # We query by the ID provided by Supabase Auth
        return await self.get_by_id(
            user_id=auth_user.user.id,
            current_user_id=auth_user.user.id
        )

    async def update(
        self,
        user_id: str,
        user_in: dict,
        current_user_id: str,
        is_admin: bool = False
    ) -> Optional[dict]:
        if not is_admin and user_id != current_user_id:
            raise ValueError(ERROR_NOT_AUTHORIZED)

        # Define which fields are safe for a user to change themselves
        allowed_fields = {"full_name", "phone", "user_name"}
        safe_data = {k: v for k, v in user_in.items() if k in allowed_fields}

        if not safe_data:
            return None

        response = await asyncio.to_thread(
            lambda: self.client.table("users")
                .update(safe_data)
                .eq("user_id", user_id)
                .execute()
        )

        return response.data[0] if response.data else None

    async def delete(
        self,
        user_id: str,
        current_user_id: str,
        is_admin: bool = False
    ) -> bool:
        if not is_admin and user_id != current_user_id:
            raise ValueError(ERROR_NOT_AUTHORIZED)

        # Soft delete logic
        response = await asyncio.to_thread(
            lambda: self.client.table("users")
                .update({"is_active": False})
                .eq("user_id", user_id)
                .execute()
        )

        return bool(response.data)