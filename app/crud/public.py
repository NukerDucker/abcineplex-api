from supabase import Client
from typing import List

class CRUDPublic:
    def __init__(self, supabase_client: Client):
        self.client = supabase_client

    async def get_hero_carousel(self) -> List[dict]:
        response = self.client.table("hero_carousel")\
            .select("*")\
            .eq("is_active", True)\
            .order("display_order")\
            .execute()
        return response.data

    async def get_promo_events(self) -> List[dict]:
        response = self.client.table("promo_events")\
            .select("*")\
            .eq("is_active", True)\
            .order("created_at")\
            .execute()
        return response.data
