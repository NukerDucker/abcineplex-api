from supabase import Client
from typing import List, Optional
from app.schemas.public import HeroSlideCreate, HeroSlideUpdate, PromotionCreate, PromotionUpdate

class CRUDPublic:
    def __init__(self, supabase_client: Client):
        self.client = supabase_client

    # --- Hero Carousel ---
    async def create_hero_slide(self, slide: HeroSlideCreate) -> dict:
        data = slide.model_dump(mode='json')
        response = self.client.table("hero_carousel").insert(data).execute()
        return response.data[0]

    async def update_hero_slide(self, slide_id: str, slide_in: HeroSlideUpdate) -> Optional[dict]:
        data = slide_in.model_dump(exclude_unset=True, mode='json')
        if not data:
            return None # Or get by id
        response = self.client.table("hero_carousel").update(data).eq("id", slide_id).execute()
        if response.data:
            return response.data[0]
        return None

    async def delete_hero_slide(self, slide_id: str) -> bool:
        response = self.client.table("hero_carousel").delete().eq("id", slide_id).execute()
        return len(response.data) > 0

    async def get_hero_carousel(self) -> List[dict]:
        response = self.client.table("hero_carousel")\
            .select("*")\
            .eq("is_active", True)\
            .order("display_order")\
            .execute()
        return response.data

    # --- Promotions ---
    async def create_promotion(self, promo: PromotionCreate) -> dict:
        data = promo.model_dump(mode='json')
        response = self.client.table("promo_events").insert(data).execute()
        return response.data[0]

    async def update_promotion(self, promo_id: str, promo_in: PromotionUpdate) -> Optional[dict]:
        data = promo_in.model_dump(exclude_unset=True, mode='json')
        if not data:
            return None
        response = self.client.table("promo_events").update(data).eq("id", promo_id).execute()
        if response.data:
            return response.data[0]
        return None

    async def delete_promotion(self, promo_id: str) -> bool:
        response = self.client.table("promo_events").delete().eq("id", promo_id).execute()
        return len(response.data) > 0

    async def get_promo_events(self) -> List[dict]:
        response = self.client.table("promo_events")\
            .select("*")\
            .eq("is_active", True)\
            .order("created_at")\
            .execute()
        return response.data
