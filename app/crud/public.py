from supabase import Client
from typing import List, Optional
from app.schemas.public import HeroSlideCreate, HeroSlideUpdate, PromotionCreate, PromotionUpdate
import asyncio


class CRUDPublic:
    """Optimized public content CRUD operations"""
    __slots__ = ('client',)

    def __init__(self, supabase_client: Client):
        self.client = supabase_client

    async def create_hero_slide(self, slide: HeroSlideCreate) -> dict:
        """Create hero carousel slide"""
        data = slide.model_dump(mode='json')
        response = await asyncio.to_thread(
            lambda: self.client.table("hero_carousel").insert(data).execute()
        )
        return response.data[0]

    async def get_hero_slide(self, slide_id: str) -> Optional[dict]:
        """Get hero slide by ID"""
        response = await asyncio.to_thread(
            lambda: self.client.table("hero_carousel")
                .select("*")
                .eq("id", slide_id)
                .maybe_single()
                .execute()
        )
        return response.data

    async def update_hero_slide(self, slide_id: str, slide_in: HeroSlideUpdate) -> Optional[dict]:
        """Update hero slide and fetch updated record"""
        data = slide_in.model_dump(exclude_unset=True, mode='json')
        if not data:
            return await self.get_hero_slide(slide_id)

        # Execute update
        await asyncio.to_thread(
            lambda: self.client.table("hero_carousel")
                .update(data)
                .eq("id", slide_id)
                .execute()
        )

        # Fetch and return updated record
        return await self.get_hero_slide(slide_id)

    async def delete_hero_slide(self, slide_id: str) -> bool:
        """Delete hero slide"""
        response = await asyncio.to_thread(
            lambda: self.client.table("hero_carousel").delete().eq("id", slide_id).execute()
        )
        return bool(response.data)

    async def get_hero_carousel(self) -> List[dict]:
        """Get active hero carousel slides ordered by display priority"""
        response = await asyncio.to_thread(
            lambda: self.client.table("hero_carousel")
                .select("*")
                .eq("is_active", True)
                .order("display_order")
                .execute()
        )
        return response.data or []

    async def create_promotion(self, promo: PromotionCreate) -> dict:
        """Create promotional event"""
        data = promo.model_dump(mode='json')
        response = await asyncio.to_thread(
            lambda: self.client.table("promotions").insert(data).execute()
        )
        return response.data[0]

    async def get_promotion(self, promo_id: str) -> Optional[dict]:
        """Get promotion by ID"""
        response = await asyncio.to_thread(
            lambda: self.client.table("promotions")
                .select("*")
                .eq("id", promo_id)
                .maybe_single()
                .execute()
        )
        return response.data

    async def update_promotion(self, promo_id: str, promo_in: PromotionUpdate) -> Optional[dict]:
        """Update promotion and fetch updated record"""
        data = promo_in.model_dump(exclude_unset=True, mode='json')
        if not data:
            return await self.get_promotion(promo_id)

        # Execute update
        await asyncio.to_thread(
            lambda: self.client.table("promotions")
                .update(data)
                .eq("id", promo_id)
                .execute()
        )

        # Fetch and return updated record
        return await self.get_promotion(promo_id)

    async def delete_promotion(self, promo_id: str) -> bool:
        """Delete promotion"""
        response = await asyncio.to_thread(
            lambda: self.client.table("promotions").delete().eq("id", promo_id).execute()
        )
        return bool(response.data)

    async def get_promo_events(self) -> List[dict]:
        """Get active promotional events"""
        response = await asyncio.to_thread(
            lambda: self.client.table("promotions")
                .select("*")
                .eq("is_active", True)
                .order("created_at")
                .execute()
        )
        return response.data or []

    async def get_promotions(self) -> List[dict]:
        """Alias for get_promo_events for backward compatibility"""
        return await self.get_promo_events()
