"""
CRUD operations for user profiles
Handles user profile information separate from user credentials
"""
from supabase import Client
from typing import List, Optional
from uuid import UUID
from app.schemas.profile import ProfileUpdate
from app.core.exceptions import UnauthorizedException, NotFoundException
import asyncio


class CRUDProfile:
    """Optimized profile CRUD operations"""
    __slots__ = ('client',)

    def __init__(self, supabase_client: Client):
        self.client = supabase_client

    async def get_profile(
        self,
        user_id: UUID,
        current_user_id: UUID,
        is_admin: bool = False
    ) -> Optional[dict]:
        """Get user profile by user ID with authorization check"""
        # Authorization check
        if not is_admin and user_id != current_user_id:
            raise UnauthorizedException()

        response = await asyncio.to_thread(
            lambda: self.client.table("profiles")
                .select("*")
                .eq("id", str(user_id))
                .maybe_single()
                .execute()
        )

        return response.data

    async def get_profiles(
        self,
        skip: int = 0,
        limit: int = 20,
        is_admin: bool = False
    ) -> List[dict]:
        """Get all user profiles (admin only)"""
        if not is_admin:
            raise UnauthorizedException()

        response = await asyncio.to_thread(
            lambda: self.client.table("profiles")
                .select("*")
                .order("updated_at", desc=True)
                .range(skip, skip + limit - 1)
                .execute()
        )

        return response.data or []

    async def update_profile(
        self,
        user_id: UUID,
        profile_in: ProfileUpdate,
        current_user_id: UUID,
        is_admin: bool = False
    ) -> Optional[dict]:
        """Update user profile with authorization check"""
        # Authorization check
        if not is_admin and user_id != current_user_id:
            raise UnauthorizedException()

        data = profile_in.model_dump(exclude_unset=True, mode='json')
        if not data:
            return await self.get_profile(user_id, current_user_id, is_admin)

        response = await asyncio.to_thread(
            lambda: self.client.table("profiles")
                .update(data)
                .eq("id", str(user_id))
                .select()
                .maybe_single()
                .execute()
        )

        return response.data

    async def get_loyalty_points(
        self,
        user_id: UUID,
        current_user_id: UUID,
        is_admin: bool = False
    ) -> Optional[int]:
        """Get user's loyalty points"""
        # Authorization check
        if not is_admin and user_id != current_user_id:
            raise UnauthorizedException()

        profile = await self.get_profile(user_id, current_user_id, is_admin)
        return profile.get("loyalty_points", 0) if profile else None

    async def add_loyalty_points(
        self,
        user_id: UUID,
        points: int,
        is_admin: bool = False
    ) -> Optional[dict]:
        """Add loyalty points to user (admin only)"""
        if not is_admin:
            raise UnauthorizedException()

        if points < 0:
            raise ValueError("Points cannot be negative")

        # Get current points
        profile = await self.get_profile(user_id, user_id, is_admin)
        if not profile:
            raise NotFoundException("Profile", str(user_id))

        current_points = profile.get("loyalty_points", 0)
        new_points = current_points + points

        response = await asyncio.to_thread(
            lambda: self.client.table("profiles")
                .update({"loyalty_points": new_points})
                .eq("id", str(user_id))
                .select()
                .maybe_single()
                .execute()
        )

        return response.data

    async def redeem_loyalty_points(
        self,
        user_id: UUID,
        points: int,
        current_user_id: UUID,
        is_admin: bool = False
    ) -> Optional[dict]:
        """Redeem loyalty points (user or admin)"""
        # Authorization check
        if not is_admin and user_id != current_user_id:
            raise UnauthorizedException()

        if points <= 0:
            raise ValueError("Points to redeem must be positive")

        # Get current points
        profile = await self.get_profile(user_id, current_user_id, is_admin)
        if not profile:
            raise NotFoundException("Profile", str(user_id))

        current_points = profile.get("loyalty_points", 0)
        if current_points < points:
            raise ValueError(f"Insufficient loyalty points. Available: {current_points}")

        new_points = current_points - points

        response = await asyncio.to_thread(
            lambda: self.client.table("profiles")
                .update({"loyalty_points": new_points})
                .eq("id", str(user_id))
                .select()
                .maybe_single()
                .execute()
        )

        return response.data
